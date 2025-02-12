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
import math



# Debug flag, fake the data collection if True
DEBUG = False
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

def close_program(ser,status, chandle, stop_reason=" "):
    for current_device_number in range(8):
        command_485.servo_control(current_device_number, ser, 0)
    if ser.is_open:
        ser.close()
    r_pico.pico_close(status, chandle)
    print (" Program is stopped: ", stop_reason)
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
    axs[2].plot(acc_data, label="acceleration")
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
                dataRUL, err_record, err_sts = command_485.get_all_RUL_pack(ser, current_device_number + 1, AQ_data_length * 4)

                # ge pico acc data and its rms
                chARange, pico_data = r_pico.get_pico_values(status, chandle, runblock_settings, chARange)

                if not err_sts:
                    RUL_newest_numbers[j]=RUL_newest_numbers[j]+1
                    Rul_folder_name = f"{Data_folder}/Update_data/RUL_data/RUL_{current_device_number + 1}"
                    CSV_file_name = f"{Rul_folder_name}/RUL_Data_{current_device_number + 1}_{RUL_newest_numbers[j]}.csv"
                    # Data_handle.data_update_RUL_csv(ser, current_device_number + 1, CSV_file_name, dataRUL, retries=5, delay=1)
                    Data_handle.data_update_RUL_parquet(ser, current_device_number + 1, motor_cond,CSV_file_name, dataRUL
                                                        , retries=5, delay=1)  # save by parquet file

                    # print the collection  message
                    print(f'Device' + str(current_device_number+1) + ' RUL data ' + str(
                        RUL_newest_numbers[j]) + ' is saved, time:', time.strftime(" %H:%M:%S", time.localtime()))
                    plot_sensory_data_pico(figs[j], axs_list[j], dataRUL['voltage_alpha'], dataRUL['voltage_beta'],
                                           dataRUL['current_alpha'], dataRUL['current_beta'], pico_data)
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
                    acc_alarm_count=acc_alarm_count+1 if acc_alarm_count>5 else close_program(ser, status, chandle, f'Vibration alarm{acc_rms:.5f}' )



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

                # calibrate the CT offset
                dataRUL, _, _ = command_485.get_all_RUL_pack(ser, online_device_indices[i]  + 1,AQ_data_length*4 )
                offset_alpha= (np.mean(np.array(dataRUL['current_alpha']))-32767)/32768
                offset_beta = (np.mean(np.array(dataRUL['current_beta']))-32767)/32768
                command_485.set_ct_offset(ser, online_device_indices[i] + 1, 0.1, offset_alpha, offset_beta, 'CT')

                # wait ASRAM update
                time.sleep(1)
                # plot the sensory data after calibration
                dataRUL, _, _ = command_485.get_all_RUL_pack(ser, online_device_indices[i] + 1, AQ_data_length)
                plot_sensory_data_pico(figs[i], axs_list[i], dataRUL['voltage_alpha'], dataRUL['voltage_beta'],
                                       dataRUL['current_alpha'], dataRUL['current_beta'])
                # servo on and wait for the motor to be ready
                command_485.servo_control(online_device_indices[i] + 1, ser, 1)
                command_485.reset_AQbox_FAST(ser, online_device_indices[i] + 1)
                time.sleep(1)

            # run the first collection
            collect_rul_data(ser, online_device_indices, RUL_newest_numbers, Data_folder, AQ_data_length, figs, axs_list)

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
                    time.sleep(1)  # 減少 CPU 使用率，確保任務按時執行
            except KeyboardInterrupt:
                close_program(ser, status, chandle, " interrupted by user.")

    except Exception as ex:
        print("An error occurred: ", ex)

    finally:
        close_program(ser, status, chandle, "Program stopped by exception.")

# if __name__ == "__main__":
#     main()
main()
