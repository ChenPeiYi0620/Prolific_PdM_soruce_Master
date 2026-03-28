import sys
import time
import serial
from serial.tools import list_ports
import command_485
import Data_handle
import os
import Motor_global_vars
import numpy as np
import threading
import schedule
import Data_handle_in_IPC
from threading import Lock
import matplotlib.pyplot as plt
import rul_pico_functions as r_pico
from picosdk.ps4000 import ps4000 as ps
from rul_features.rul_data_read import read_rul_data
import re,shutil,csv
import math



# Debug flag if true the program will run debug mode, not collect data but only run the scheduling and plot demo functions
# no device connection recquired in debug mode, and the plot will show test data
DEBUG = False
# DEBUG = True # for schedule and obsever test 

# ccae test counter 
CCAE_test_mode=True 
ccae_counter = {"count": 0, "times": 100}



# FAST data collection method flag
FAST_in_IPC = True
# record the package error times
total_err_count = 0

# parameter declaration
MAX_RETRIES = Motor_global_vars.max_tries  # Max retry times in each collection cycle
FAST_PERIOD = Motor_global_vars.fast_update_period  # Period for FAST data collection
RUL_PERIOD = Motor_global_vars.rul_update_period  # Period for RUL data collection
AQ_data_length = Motor_global_vars.data_length  # Signal length

# peripheral device declaration
status, chandle, runblock_settings, chARange = None, None, None, None
acc_alarm_count=0


# Initialize lock for synchronization
lock = Lock()

# simple plot function
plt.ion()  # 開啟互動模式

def clear_terminal():
    """清除終端畫面，確保執行時只有一個執行緒進入"""
    with lock:  # 確保只有一個執行緒在執行此操作
        os.system('cls' if os.name == 'nt' else 'clear')
        print("終端已清除")

def close_program(ser,status, chandle, stop_reason=" ", Data_folder=""):
    for current_device_number in range(8):
        print('closing device ', current_device_number+1)
        command_485.servo_control(current_device_number, ser, 0)
    if ser.is_open:
        ser.close()
    r_pico.pico_close(status, chandle)
    print (" Program is stopped: ", stop_reason)
    print ("program stopped, calibrating voltages ...")
    list_voltage_thd(f"{Data_folder}/Update_data/RUL_data/RUL_{3}")

    input("按 Enter 鍵退出...")
    sys.exit()

def plot_sensory_data(fig,axs, v_alpha, v_beta, i_alpha, i_beta, flux_alpha, flux_beta, torque_v):
    # 將所有數據轉換為 numpy 陣列
    v_alpha, v_beta = np.array(v_alpha), np.array(v_beta)
    i_alpha, i_beta = np.array(i_alpha), np.array(i_beta)
    flux_alpha, flux_beta = np.array(flux_alpha), np.array(flux_beta)
    torque_v = np.array(torque_v)

    # 清除所有子圖的內容
    for ax in axs:
        ax.clear()

    # 子圖1：繪製 v_alpha 與 v_beta
    axs[0].plot(v_alpha, label="v_alpha")
    axs[0].plot(v_beta, label="v_beta")
    axs[0].set_title("Voltage")
    axs[0].legend()

    # 子圖2：繪製 i_alpha 與 i_beta
    axs[1].plot(i_alpha, label="i_alpha")
    axs[1].plot(i_beta, label="i_beta")
    axs[1].set_title("Current")
    axs[1].legend()

    # 子圖3：繪製 flux_alpha 與 flux_beta
    axs[2].plot(flux_alpha, label="flux_alpha")
    axs[2].plot(flux_beta, label="flux_beta")
    axs[2].set_title("Flux")
    axs[2].legend()

    # 子圖4：繪製 torque_v
    axs[3].plot(torque_v, label="torque_v")
    axs[3].set_title("Torque")
    axs[3].legend()

    fig.canvas.draw()
    plt.pause(0.1)  # 非阻塞顯示

def plot_sensory_data_pico(fig,axs, v_alpha, v_beta, i_alpha, i_beta, acc_data=None):
    # 將所有數據轉換為 numpy 陣列
    v_alpha, v_beta = np.array(v_alpha), np.array(v_beta)
    i_alpha, i_beta = np.array(i_alpha), np.array(i_beta)
    acc_data = np.array(acc_data)

    # 清除所有子圖的內容
    for ax in axs:
        ax.clear()

    # 子圖1：繪製 v_alpha 與 v_beta
    axs[0].plot(v_alpha, label="v_alpha")
    axs[0].plot(v_beta, label="v_beta")
    axs[0].set_title("Voltage")
    axs[0].legend()

    # 子圖2：繪製 i_alpha 與 i_beta
    axs[1].plot(i_alpha, label="i_alpha")
    axs[1].plot(i_beta, label="i_beta")
    axs[1].set_title("Current")
    axs[1].legend()

    # 子圖3：繪製 flux_alpha 與 flux_beta
    global chARange
    pico_gain_str = [k for k, v in ps.PS4000_RANGE.items() if v == chARange]
    axs[2].plot(acc_data, label=f"acceleration: {pico_gain_str}")
    axs[2].set_title("Pico acc result ")
    axs[2].legend()

    fig.canvas.draw()
    plt.pause(0.1)  # 非阻塞顯示

# check the newest data number of the recorded RUL data (scv or parquet)
def get_newest_data_number(Rul_folder_name):
    files = [f for f in os.listdir(Rul_folder_name) if f.endswith((".csv", ".parquet"))]
    if not files:
        return 0
    newest_file = max(files, key=lambda f: os.path.getmtime(os.path.join(Rul_folder_name, f)))
    return int(newest_file.rsplit("_", 1)[-1].split(".")[0]) if newest_file.rsplit("_", 1)[-1].split(".")[
        0].isdigit() else 0

def check_and_create_folders(Data_folder, online_device_indices, RUL_newest_numbers):
    if not os.path.exists(Data_folder):
        Data_folder = "."

    if not os.path.exists(f"{Data_folder}/Update_data/FAST_data"):
        os.makedirs(f"{Data_folder}/Update_data/FAST_data")

    for i in range(len(online_device_indices)):
        Rul_folder_name = f"{Data_folder}/Update_data/RUL_data/RUL_{online_device_indices[i] + 1}"
        if os.path.exists(Rul_folder_name):
            RUL_newest_numbers[i] = get_newest_data_number(Rul_folder_name)
        else:
            os.makedirs(Rul_folder_name)

    return Data_folder, RUL_newest_numbers

# setup serial port
def find_AQbox_port():
    ports = list_ports.comports()
    for port in ports:
        if "Prolific PL2303GC" in port.description or "USB Serial Port" in port.description:
            return port.device
    DEBUG or sys.exit("Failed to open serial port")

def AQbox_serial_set_up(COM):
    ser = serial.Serial()
    ser.port = COM
    ser.baudrate = 921600 # for NTU quick data collection
    # ser.baudrate = 115200 # for PEWC stable data collection
    ser.bytesize = serial.EIGHTBITS
    ser.parity = serial.PARITY_NONE
    ser.stopbits = serial.STOPBITS_TWO
    ser.timeout = 0.05
    ser.writeTimeout = 0.05
    ser.xonxoff = False
    ser.rtscts = False
    ser.dsrdtr = False
    return ser

def collect_fast_data(ser, online_device_indices, Data_folder, AQ_data_length, figs,  axs_list):
    """Function to collect FAST data while ensuring mutual exclusion."""
    with lock:

        if DEBUG:
            print("Collecting FAST data..., current time:", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
            return # Debugging
        for k, current_device_number in enumerate(online_device_indices):
            retries = 0
            while retries < MAX_RETRIES:
                # get motor operating condition
                motor_cond, cond_err_sts = command_485.get_cond_pack(ser, current_device_number + 1, 3)
                # get motor fault status
                motor_cn_sts, cn_sts_err_sts = command_485.get_cn_pack(ser, current_device_number + 1, 3)
                if cond_err_sts or cn_sts_err_sts:
                    break # Skip this collection if condition flags are not received

                if not FAST_in_IPC:
                    # get FAST data (from AQbox)
                    unpack_fast_data, err_record, err_sts = command_485.get_all_FAST_pack(ser, current_device_number + 1, AQ_data_length)

                else :
                    # start_time = time.time()
                    # get FAST data (from IPC calculation)
                    dataRUL, err_record, err_sts = command_485.get_all_RUL_pack(ser, current_device_number + 1,AQ_data_length * 2)
                    # end_time = time.time()
                    # print("FAST collect time：{:.6f} s".format(end_time - start_time))

                    # convert the data to physical value
                    # voltage alpha beta collect from PEWC is actually Va and Vc
                    voltage_a_SI = Data_handle.u16_to_true_data(np.array(dataRUL['voltage_alpha']),Motor_global_vars.Base_voltage)
                    voltage_c_SI = Data_handle.u16_to_true_data(np.array(dataRUL['voltage_beta']),Motor_global_vars.Base_voltage)
                    current_alpha_SI = Data_handle.u16_to_true_data(np.array(dataRUL['current_alpha']),Motor_global_vars.Base_current)
                    current_beta_SI = Data_handle.u16_to_true_data(np.array(dataRUL['current_beta']),Motor_global_vars.Base_current)

                    torque_raw, flux_alpha_IPC,flux_beta_IPC, v_alpha, v_beta, power_sts = Data_handle_in_IPC. estimate_torque(voltage_a_SI, voltage_c_SI, current_alpha_SI, current_beta_SI, debug=False)
                    # get the average torque
                    torque =np.mean(torque_raw[-Motor_global_vars.data_length:])
                    motor_cn_sts, fund_freq, minus1_freq=Data_handle_in_IPC.get_cn_sts_list(current_alpha_SI,current_beta_SI)

                    motor_cond['torque']=torque*32768+32767
                    motor_cond['power']=power_sts['Power_E']/1000*32768+32767

                    global total_err_count
                    print(f'IPC collection fail times: {total_err_count}')
                    # record the error times
                    total_err_count=total_err_count+sum(err_record)

                    # update the motor condition by IPC calculation result
                    err_record=err_record[-Motor_global_vars.data_length:] # only record the latest data
                    unpack_fast_data = {
                        # convert IPC calculation result to MCU data format
                        'flux_alpha': np.array(flux_alpha_IPC[-Motor_global_vars.data_length:]) * 32768 + 32767,
                        'flux_beta': np.array(flux_beta_IPC[-Motor_global_vars.data_length:]) * 32768 + 32767,
                        'error_record': err_record,
                    }

                if not err_sts:
                    # save the data to csv fi-le
                    CSV_file_name = f"{Data_folder}/Update_data/FAST_data/Data_{current_device_number + 1}.csv"
                    Data_handle.data_update_FAST_csv(CSV_file_name, motor_cond, motor_cn_sts, unpack_fast_data, err_record,
                                                     retries=3, delay=5, device_number=current_device_number + 1)
                    print(f" Device {current_device_number + 1} FAST updated, time:", time.strftime(" %H:%M:%S", time.localtime()))

                    # Update the plot with new data
                    # simple_plot(np.array(dataRUL['current_alpha']), np.array(dataRUL['current_beta']), axs)
                    # multi_plot(dataRUL['voltage_alpha'], dataRUL['voltage_beta'], dataRUL['current_alpha'], dataRUL['current_beta'], axs)
                    plot_sensory_data(figs[k], axs_list[k], v_alpha, v_beta, current_alpha_SI, current_beta_SI
                                      , flux_alpha_IPC, flux_beta_IPC, torque_raw)

                    break
                else:
                    retries += 1


def collect_rul_data(ser, online_device_indices, RUL_newest_numbers, Data_folder, AQ_data_length, figs, axs_list):
    

    """Function to collect RUL data while ensuring mutual exclusion."""
    with lock:
        global status, chandle, runblock_settings, chARange
        
        if CCAE_test_mode:
            ccae_counter["count"] += 1
        if ccae_counter["count"] >= ccae_counter["times"]:
            ccae_counter["count"] = 0
            print(f"CCAETest: {ccae_counter['count']} times, close the program")
            close_program(ser, status, chandle, "CCAETest: close the program after 20 times", Data_folder)
        
        if DEBUG:
            print("Collecting RUL data..., current time:", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
            return # Debugging
        for j in range(len(online_device_indices)):
            current_device_number = online_device_indices[j]
            retries = 0
            # run the pico block
            r_pico.runblock_pico_A(status, chandle, runblock_settings)

            # get motor operating condition
            motor_cond, cond_err_sts = command_485.get_cond_pack(ser, current_device_number + 1, 3)

            while retries < MAX_RETRIES:
                timemow=time.time()
                # dataRUL, err_record, err_sts = command_485.get_all_RUL_pack(ser, current_device_number + 1, AQ_data_length * 4)
                dataRUL, err_record, err_sts = command_485.get_all_RUL_pack_bulk(ser, current_device_number + 1, AQ_data_length * 4)
                print(f'collect time:{time.time()-timemow}')
                # ge pico acc data and its rms
                chARange, pico_data = r_pico.get_pico_values(status, chandle, runblock_settings, chARange)

                if not err_sts:
                    RUL_newest_numbers[j]=RUL_newest_numbers[j]+1
                    Rul_folder_name = f"{Data_folder}/Update_data/RUL_data/RUL_{current_device_number + 1}"
                    CSV_file_name = f"{Rul_folder_name}/RUL_Data_{current_device_number + 1}_{RUL_newest_numbers[j]}.csv"
                   
                    # Data_handle.data_update_RUL_csv(ser, current_device_number + 1, CSV_file_name, dataRUL, retries=5, delay=1)
                    Data_handle.data_update_RUL_parquet(ser, current_device_number + 1, motor_cond,CSV_file_name, dataRUL, pico_data
                                                        , retries=5, delay=1)  # save by parquet file


                    
                    # essemble_file_name = f"{Rul_folder_name}/RUL_Data_{current_device_number + 1}.h5"
                    # Data_handle.data_update_RUL_essemble(ser, current_device_number + 1, motor_cond,essemble_file_name, dataRUL, pico_data
                    #                                     , retries=5, delay=1)  # save by essemble h5 file
                    
                    # print the collection  message
                    print(f'Device' + str(current_device_number+1) + ' RUL data ' + str(
                        RUL_newest_numbers[j]) + ' is saved, time:', time.strftime(" %H:%M:%S", time.localtime()))
                    plot_sensory_data_pico(figs[j], axs_list[j], dataRUL['voltage_alpha'], dataRUL['voltage_beta'],
                                           dataRUL['current_alpha'], dataRUL['current_beta'], pico_data)

                    if RUL_newest_numbers[j]>=Motor_global_vars.collection_times:
                        close_program(ser, status, chandle, f"reach the collection times {Motor_global_vars.collection_times}", Data_folder)
                    break
                else:
                    retries += 1

        # record the error times
        global total_err_count
        total_err_count = total_err_count + sum(err_record)


# scheduling : motor acceleration check
def motor_acc_check(ser,online_device_indices):
        global status, chandle, runblock_settings,chARange
        with lock:
            for i in range(len(online_device_indices)):
                # print(f'acc status check for device {online_device_indices[i]+1}, time : {time.strftime("%H:%M:%S", time.localtime())}')
                # run the pico block to check acc level
                r_pico.runblock_pico_A(status, chandle, runblock_settings)
                # ge pico acc data and its rms
                chARange, pico_data = r_pico.get_pico_values(status, chandle, runblock_settings, chARange)
                acc_rms = np.sqrt(np.mean((pico_data - np.mean(pico_data)) ** 2))
                print(f' Device {online_device_indices[i]+1} vibration rms : {acc_rms:.5f}, time : {time.strftime("%H:%M:%S", time.localtime())}')
                if acc_rms>Motor_global_vars.acc_threshold:
                    global acc_alarm_count #stop collection if vibration alarm trigger too many times
                    acc_alarm_count=acc_alarm_count+1 if acc_alarm_count<3 else close_program(ser, status, chandle, f'Vibration alarm{acc_rms:.5f}, trigger times: {acc_alarm_count}')

# calibrating collected voltages file by file
def list_voltage_thd(Normal_subfolders):
    # 列出目標資料夾下的檔案重建誤差以找出離群值
    """取得指定工況資料夾下的所有檔案，並找出離群值"""
    # 在 Normal_subfolders 建立子資料夾 voltage_plot
    voltage_plot_folder = os.path.join(Normal_subfolders, "voltage_plot")
    outlier_folder = os.path.join(Normal_subfolders, "outlier")
    if not os.path.exists(voltage_plot_folder):
        os.makedirs(voltage_plot_folder)
    if not os.path.exists(outlier_folder):
        os.makedirs(outlier_folder)
    # 如果 outlier_folder 內已有檔案則直接跳過
    if len(os.listdir(outlier_folder)) > 0:
        print(f"Outlier folder {outlier_folder} is not empty, skipping.")
        return []

    # 依檔案編號排序
    parquet_files = [os.path.join(Normal_subfolders, f) for f in os.listdir(Normal_subfolders) if
                     f.endswith(".parquet")]
    parquet_files = sorted(parquet_files,
                           key=lambda x: int(re.search(r"(\d+)\.parquet$", os.path.basename(x)).group(1)))
    print(parquet_files)
    voltage_thd_list = []
    alpha_thd_list = []
    for file_path in parquet_files:
        if not os.path.exists(file_path):
            print(f"File {file_path} does not exist.")
            continue
        # 讀取資料
        df = read_rul_data(file_path, force_recompute=True)
        if df is None:
            print(f"File {file_path} could not be read, skipping.")
            continue
        voltage_alpha = np.array(df["Voltage alpha downsample"])
        voltage_beta = np.array(df["Voltage beta downsample"])
        voltage_alpha_thd = df["Voltage alpha thd"]
        voltage_beta_thd = df["Voltage beta thd"]

        # 畫圖並儲存
        plt.figure(figsize=(12, 6))
        plt.plot(voltage_alpha, label=f'Voltage Alpha thd: {voltage_alpha_thd[0]:.4f}')
        plt.plot(voltage_beta, label=f'Voltage Beta thd: {voltage_beta_thd[0]:.4f}')
        plt.title(f'Voltage Alpha/Beta: {os.path.basename(file_path)}')
        plt.xlabel('Sample')
        plt.ylabel('Voltage')
        plt.legend()
        save_path = os.path.join(voltage_plot_folder, os.path.splitext(os.path.basename(file_path))[0] + '_voltage.png')
        plt.savefig(save_path)
        plt.close()
        alpha_thd_list.append(voltage_alpha_thd[0])
        voltage_thd_list.append(
            (os.path.splitext(os.path.basename(file_path))[0], voltage_alpha_thd[0], voltage_beta_thd[0]))
        # print(f"File: {file_path}, Voltage Alpha THD: {voltage_alpha_thd}, Voltage Beta THD: {voltage_beta_thd}")

    # 找出 alpha_thd_list 最大的五個值的索引並將對應的翻轉不好的電壓檔案移動到 outlier_folder
    if len(alpha_thd_list) >= Motor_global_vars.outlier_number:
        alpha_thd_array = np.array(alpha_thd_list)
        top5_indices = alpha_thd_array.argsort()[-Motor_global_vars.outlier_number:][::-1]
        for idx in top5_indices:
            src_file = parquet_files[idx]
            dst_file = os.path.join(outlier_folder, os.path.basename(src_file))
            print(f"Moving outlier file: {src_file} -> {dst_file}")
            shutil.move(src_file, dst_file)

    # 將 voltage_thd_list 存到 CSV
    csv_save_path = os.path.join(voltage_plot_folder, "voltage_thd_list.csv")
    with open(csv_save_path, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['file_path', 'voltage_alpha_thd', 'voltage_beta_thd'])
        for row in voltage_thd_list:
            writer.writerow(row)
    return voltage_thd_list


def main():
    print('AQbox data collection program start, version 1.0')

    # find and setups the AQbox port
    com = find_AQbox_port()
    ser = AQbox_serial_set_up(com)

    # setup pico device
    try:
        global status, chandle, runblock_settings, chARange
        status, chandle, runblock_settings, chARange = r_pico.pico_setup_acc(AQ_data_length * 4)
    except Exception as ex:
        print("Failed to setup Pico device: ", ex)
        input("按 Enter 鍵退出...")
        sys.exit()

    # Call plt.ion() to enable interactive mode
    plt.ion()

    try:
        ser.open()
    except Exception as ex:
        if DEBUG:
            print("Failed to open serial port: ", ex, end=' ')
            print ("Debug mode: fake data collection")
        else :
            print("Failed to open serial port: " + str(ex))
            input("按 Enter 鍵退出...")
            sys.exit()

    try:
        if DEBUG or ser.is_open:

            # check the device status
            device_status = command_485.check_device_number(ser, 0.1, Motor_global_vars.transmit_test_flag)
            online_devices = [index for index, value in enumerate(device_status) if value != 0]
            online_device_indices = [index for index, value in enumerate(device_status) if value != 0]
            RUL_newest_numbers = [1] * len(online_device_indices)
            if not online_devices:
                if DEBUG:
                    print("No online devices found, entering debug mode...")
                else:
                    print("No online devices found. Closing serial port.")
                    input("按 Enter 鍵退出...")
                    sys.exit()

            # set up figures
            n = len(online_devices)
            figs, axs_list = [], []
            for i in range(len(online_devices)):
                fig, axs = plt.subplots(3, 1, sharex=True, figsize=(6, 8))
                fig.suptitle(f"Sensor {online_devices[i] + 1} Data")
                figs.append(fig)
                axs_list.append(axs)

            # setup the data folder
            Data_folder, RUL_newest_numbers = check_and_create_folders(Motor_global_vars.Data_folder_path, online_device_indices, RUL_newest_numbers)

            # setup the plot

            # calibration CT oset and servo on the motors
            for i in range(len(online_device_indices)):
                
                # command_485.get_all_RUL_pack_bulk(ser, online_device_indices[i]+1, AQ_data_length*4)
                
                # calibrate the CT offset
                dataRUL, _, _ = command_485.get_all_RUL_pack_bulk(ser, online_device_indices[i]  + 1,AQ_data_length*4 )
                offset_alpha= (np.mean(np.array(dataRUL['current_alpha']))-32767)/32768
                offset_beta = (np.mean(np.array(dataRUL['current_beta']))-32767)/32768
                command_485.set_ct_offset(ser, online_device_indices[i] + 1, 0.1, offset_alpha, offset_beta, 'CT')

                # plot the sensory data after calibration
                plot_sensory_data_pico(figs[i], axs_list[i], dataRUL['voltage_alpha'], dataRUL['voltage_beta'],
                                       dataRUL['current_alpha'], dataRUL['current_beta'])
                # servo on and wait for the motor to be ready
                command_485.servo_control(online_device_indices[i] + 1, ser, 1)
                command_485.reset_AQbox_FAST(ser, online_device_indices[i] + 1)

                
                # wait ASRAM update
                time.sleep(2)
                print('preparing for the motor to be ready, please wait...')
                dataRUL, _, _ = command_485.get_all_RUL_pack_bulk(ser, online_device_indices[i] + 1, AQ_data_length*4)
                plot_sensory_data_pico(figs[i], axs_list[i], dataRUL['voltage_alpha'], dataRUL['voltage_beta'],
                                       dataRUL['current_alpha'], dataRUL['current_beta'])
                current_alpha_out = Data_handle.u16_to_true_data(np.array(dataRUL['current_alpha']), Motor_global_vars.Base_current)
                current_beta_out = Data_handle.u16_to_true_data(np.array(dataRUL['current_beta']), Motor_global_vars.Base_current)
                fund_freq = max(1, Data_handle.get_fundamental_freq(current_alpha_out, current_beta_out, Motor_global_vars.sampling_rate))
                print(f'fundamental frequency: {fund_freq}, rpm={fund_freq*60/2/Motor_global_vars.Motor_P}')
                m_wave_number_fft = int( Motor_global_vars.sampling_rate/fund_freq/2) # 取樣點數
                command_485.set_computation_result(ser, online_device_indices[i] + 1, delay=0.1, m_wave_number=m_wave_number_fft)


                time.sleep(1)
                
            print("All motors are ready, start data collection...")
            
            # run the first collection
            timenow = time.time()
            collect_rul_data(ser, online_device_indices, RUL_newest_numbers, Data_folder, AQ_data_length, figs, axs_list)
            
            print('rule collection run time: ', (time.time() - timenow))
            
            # 使用 schedule 定時執行
            schedule.every(Motor_global_vars.rul_update_period).seconds.do(collect_rul_data, ser, online_device_indices, RUL_newest_numbers,
                                                  Data_folder, AQ_data_length, figs, axs_list)

            # check the motor acceleration value every 5 seconds
            schedule.every(5).seconds.do(motor_acc_check, ser, online_device_indices)

            # clear the terminal every hour
            schedule.every().hour.do(clear_terminal)

            try:
                while True:
                    schedule.run_pending()  # 執行所有排程的任務
                    time.sleep(0.1)  # 減少 CPU 使用率，確保任務按時執行
            except KeyboardInterrupt:
                close_program(ser, status, chandle, " interrupted by user.", Data_folder)

    except Exception as ex:
        print("An error occurred: ", ex)

    finally:
        try :
            close_program(ser, status, chandle, "Program stopped by exception.")
        except Exception as ex:
            # print("An error occurred during program closure: ", ex)
            input("按 Enter 鍵退出...")
            sys.exit()

# if __name__ == "__main__":
#     main()
main()
