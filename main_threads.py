import sys
import time
import serial
from serial.tools import list_ports
from modules import command_485
from modules import Data_handle
import os
from modules import Motor_global_vars
import numpy as np
import schedule
from modules import Data_handle_in_IPC
from threading import Lock
import matplotlib.pyplot as plt
from modules.rul_features.rul_data_read import read_rul_data
import re,shutil,csv
import math



"""AQbox 主程式。

主要職責：
1. 與 AQbox 通訊，收集 FAST / RUL 資料。
2. 使用 IPC 演算法估測 torque 與 motor condition。
3. 儲存資料、更新監控圖並執行排程任務。
"""

"""函式索引（依流程）
1. 基礎工具: clear_terminal, close_program, true_to_u16_data
2. 估測與繪圖: estimate_torque_and_motor_cond_from_rul_data, plot_sensory_data, plot_sensory_data_pico
3. 初始化流程: find_AQbox_port, AQbox_serial_set_up, get_online_device_indices,
   build_monitor_figures, check_and_create_folders, setup_motor_before_collection
4. 週期任務: collect_fast_data, collect_rul_data
5. 排程流程: schedule_collection_jobs, run_scheduler_loop
6. 主流程: main
"""


# ==================== 全域設定區 ====================

# Debug flag if true the program will run debug mode, not collect data but only run the scheduling and plot demo functions
# no device connection recquired in debug mode, and the plot will show test data
DEBUG = False
# DEBUG = True # for schedule and obsever test 

# ccae test counter 
CCAE_test_mode=True 
ccae_counter = {"count": 0, "times": 100}



# FAST data collection method flag
FAST_in_IPC = True
# Motor condition source flag: True=IPC estimation, False=sensor packet
MOTOR_COND_FROM_IPC = True
# record the package error times
total_err_count = 0

# parameter declaration
MAX_RETRIES = Motor_global_vars.max_tries  # Max retry times in each collection cycle
FAST_PERIOD = Motor_global_vars.fast_update_period  # Period for FAST data collection
RUL_PERIOD = Motor_global_vars.rul_update_period  # Period for RUL data collection
AQ_data_length = Motor_global_vars.data_length  # Signal length
DEVICE_COUNT = 8
MAIN_LOOP_SLEEP_SEC = 0.1

# peripheral device declaration (Pico vibration monitoring removed)
status, chandle, runblock_settings, chARange = None, None, None, None


# Initialize lock for synchronization
lock = Lock()

# simple plot function
plt.ion()  # 開啟互動模式


# ==================== 通用工具區 ====================

def clear_terminal():
    """清除終端畫面，確保執行時只有一個執行緒進入"""
    with lock:  # 確保只有一個執行緒在執行此操作
        os.system('cls' if os.name == 'nt' else 'clear')
        print("終端已清除")

def close_program(ser,status, chandle, stop_reason=" ", Data_folder=""):
    """關閉程式與裝置，並在退出前執行電壓檔案校正流程。"""
    for current_device_number in range(DEVICE_COUNT):
        print('closing device ', current_device_number+1)
        command_485.servo_control(current_device_number, ser, 0)
    if ser.is_open:
        ser.close()
    print (" Program is stopped: ", stop_reason)
    print ("program stopped, calibrating voltages ...")
    list_voltage_thd(f"{Data_folder}/Update_data/RUL_data/RUL_{3}")

    input("按 Enter 鍵退出...")
    sys.exit()

def plot_sensory_data(fig,axs, v_alpha, v_beta, i_alpha, i_beta, flux_alpha, flux_beta, torque_v):
    """FAST 監控圖：顯示電壓/電流/磁通/力矩。"""
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


# ==================== 估測與監控圖區 ====================

def plot_sensory_data_pico(fig,axs, v_alpha, v_beta, i_alpha, i_beta, torque_data=None, data_is_u16=True):
    """RUL 監控圖：顯示電壓(V)、電流(A)、估測力矩(Nm)。"""
    # 將所有數據轉換為 numpy 陣列
    v_alpha, v_beta = np.array(v_alpha), np.array(v_beta)
    i_alpha, i_beta = np.array(i_alpha), np.array(i_beta)
    torque_data = np.array(torque_data) if torque_data is not None else None

    # Monitoring plot uses SI units on Y-axis.
    if data_is_u16:
        v_alpha = Data_handle.u16_to_true_data(v_alpha, Motor_global_vars.Base_voltage)
        v_beta = Data_handle.u16_to_true_data(v_beta, Motor_global_vars.Base_voltage)
        i_alpha = Data_handle.u16_to_true_data(i_alpha, Motor_global_vars.Base_current)
        i_beta = Data_handle.u16_to_true_data(i_beta, Motor_global_vars.Base_current)

    # 清除所有子圖的內容
    for ax in axs:
        ax.clear()

    # 子圖1：繪製 v_alpha 與 v_beta
    axs[0].plot(v_alpha, label="v_alpha")
    axs[0].plot(v_beta, label="v_beta")
    axs[0].set_title("Voltage (V)")
    axs[0].set_ylabel("V")
    axs[0].legend()

    # 子圖2：繪製 i_alpha 與 i_beta
    axs[1].plot(i_alpha, label="i_alpha")
    axs[1].plot(i_beta, label="i_beta")
    axs[1].set_title("Current (A)")
    axs[1].set_ylabel("A")
    axs[1].legend()

    # 子圖3：繪製估測 torque
    if torque_data is None:
        axs[2].text(0.5, 0.5, "Torque estimate unavailable", ha="center", va="center")
    else:
        axs[2].plot(torque_data, label="estimated_torque")
        axs[2].legend()
    axs[2].set_title("Estimated Torque (Nm)")
    axs[2].set_ylabel("Nm")

    fig.canvas.draw()
    plt.pause(0.1)  # 非阻塞顯示


def true_to_u16_data(true_data, pu_gain=1):
    """將實際物理量轉回 MCU 使用的 Uint16 編碼範圍。"""
    if pu_gain == 0:
        return 32768.0
    scaled = float(true_data) / float(pu_gain) * 32768.0 + 32768.0
    return float(np.clip(scaled, 0.0, 65535.0))


def estimate_torque_and_motor_cond_from_rul_data(dataRUL, base_motor_cond=None):
    """由 RUL 原始封包估測 torque 與工況。

    回傳:
        torque_raw: 力矩時序估測
        motor_cond: 可直接存檔/顯示的工況字典
        ipc_cond_err: IPC 計算是否失敗
        ipc_info: 給 terminal 顯示的 SI 資訊
    """
    motor_cond = dict(base_motor_cond) if isinstance(base_motor_cond, dict) else {}
    try:
        voltage_a_SI = Data_handle.u16_to_true_data(np.array(dataRUL['voltage_alpha']), Motor_global_vars.Base_voltage)
        voltage_c_SI = Data_handle.u16_to_true_data(np.array(dataRUL['voltage_beta']), Motor_global_vars.Base_voltage)
        current_alpha_SI = Data_handle.u16_to_true_data(np.array(dataRUL['current_alpha']), Motor_global_vars.Base_current)
        current_beta_SI = Data_handle.u16_to_true_data(np.array(dataRUL['current_beta']), Motor_global_vars.Base_current)
        torque_raw, _, _, _, _, power_sts = Data_handle_in_IPC.estimate_torque(
            voltage_a_SI, voltage_c_SI, current_alpha_SI, current_beta_SI, debug=False
        )
        torque = float(np.mean(torque_raw[-Motor_global_vars.data_length:]))
        # 以基頻估測轉速
        _, fund_freq, _ = Data_handle_in_IPC.get_cn_sts_list(current_alpha_SI, current_beta_SI)
        speed_rpm = float(max(0.0, fund_freq * 60 * 2 / Motor_global_vars.Motor_P))
        power_kw_e = float(power_sts.get('Power_E')) / 1000
        power_kw_m = float(torque * speed_rpm * math.pi / 30 / 1000)
        ipc_info = {
            'torque_nm': torque,
            'speed_rpm': speed_rpm,
            'power_kw(E)': power_kw_e,
            'power_kw(M)': power_kw_m,
            'efficiency_pct': power_kw_m / (power_kw_e + 1e-6) * 100 if power_kw_e > 1e-6 else 0.0,
        }
        if MOTOR_COND_FROM_IPC:
            motor_cond['speed'] = true_to_u16_data(speed_rpm, Motor_global_vars.Base_Speed)
            motor_cond['torque'] = true_to_u16_data(torque, Motor_global_vars.Base_Torque)
            motor_cond['power'] = true_to_u16_data(power_kw_e, Motor_global_vars.Base_Power)
        return torque_raw, motor_cond, False, ipc_info
    except Exception:
        return None, motor_cond, True, None

# check the newest data number of the recorded RUL data (scv or parquet)
def get_newest_data_number(Rul_folder_name):
    """取得指定資料夾中最新檔案的流水號。"""
    files = [f for f in os.listdir(Rul_folder_name) if f.endswith((".csv", ".parquet"))]
    if not files:
        return 0
    newest_file = max(files, key=lambda f: os.path.getmtime(os.path.join(Rul_folder_name, f)))
    return int(newest_file.rsplit("_", 1)[-1].split(".")[0]) if newest_file.rsplit("_", 1)[-1].split(".")[
        0].isdigit() else 0

def check_and_create_folders(Data_folder, online_device_indices, RUL_newest_numbers):
    """建立必要資料夾並初始化每顆馬達的 RUL 檔案編號。"""
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
    """自動尋找 AQbox 對應序列埠。"""
    ports = list_ports.comports()
    for port in ports:
        if "Prolific PL2303GC" in port.description or "USB Serial Port" in port.description:
            return port.device
    DEBUG or sys.exit("Failed to open serial port")

def AQbox_serial_set_up(COM):
    """建立並設定序列埠參數。"""
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


def update_rul_monitor_plot(fig, axs, data_rul):
    """更新單顆馬達 RUL 監控圖（SI 單位）。"""
    torque_raw, _, _, _ = estimate_torque_and_motor_cond_from_rul_data(data_rul)
    plot_sensory_data_pico(
        fig,
        axs,
        data_rul['voltage_alpha'],
        data_rul['voltage_beta'],
        data_rul['current_alpha'],
        data_rul['current_beta'],
        torque_raw,
    )


def setup_motor_before_collection(ser, device_idx, fig, axs):
    """單顆馬達開機前處理：CT 校正、伺服啟動、監控預覽。"""
    # 1) 取一次資料做 CT offset 校正
    data_rul, _, _ = command_485.get_all_RUL_pack_bulk(ser, device_idx + 1, AQ_data_length * 4)
    offset_alpha = (np.mean(np.array(data_rul['current_alpha'])) - 32767) / 32768
    offset_beta = (np.mean(np.array(data_rul['current_beta'])) - 32767) / 32768
    command_485.set_ct_offset(ser, device_idx + 1, 0.1, offset_alpha, offset_beta, 'CT')
    update_rul_monitor_plot(fig, axs, data_rul)

    # 2) 伺服開啟與 FAST 重置
    command_485.servo_control(device_idx + 1, ser, 1)
    command_485.reset_AQbox_FAST(ser, device_idx + 1)

    # 3) 等待更新後再取一次資料
    time.sleep(2)
    print('preparing for the motor to be ready, please wait...')
    data_rul, _, _ = command_485.get_all_RUL_pack_bulk(ser, device_idx + 1, AQ_data_length * 4)
    update_rul_monitor_plot(fig, axs, data_rul)

    # 4) 用電流基頻設定 IPC 計算視窗
    current_alpha_out = Data_handle.u16_to_true_data(np.array(data_rul['current_alpha']), Motor_global_vars.Base_current)
    current_beta_out = Data_handle.u16_to_true_data(np.array(data_rul['current_beta']), Motor_global_vars.Base_current)
    fund_freq = max(1, Data_handle.get_fundamental_freq(current_alpha_out, current_beta_out, Motor_global_vars.sampling_rate))
    print(f'fundamental frequency: {fund_freq}, rpm={fund_freq*60*2/Motor_global_vars.Motor_P}')
    m_wave_number_fft = int(Motor_global_vars.sampling_rate / fund_freq / 2)
    command_485.set_computation_result(ser, device_idx + 1, delay=0.1, m_wave_number=m_wave_number_fft)
    time.sleep(1)


def get_online_device_indices(ser):
    """取得目前在線馬達索引清單。"""
    device_status = command_485.check_device_number(ser, 0.1, Motor_global_vars.transmit_test_flag)
    return [index for index, value in enumerate(device_status) if value != 0]


def build_monitor_figures(device_indices):
    """依據在線馬達數建立監控視窗。"""
    figs, axs_list = [], []
    for device_idx in device_indices:
        fig, axs = plt.subplots(3, 1, sharex=True, figsize=(6, 8))
        fig.suptitle(f"Sensor {device_idx + 1} Data")
        figs.append(fig)
        axs_list.append(axs)
    return figs, axs_list


def schedule_collection_jobs(ser, online_device_indices, rul_newest_numbers, rul_collected_counts, data_folder, figs, axs_list):
    """註冊定時任務。"""
    schedule.every(Motor_global_vars.rul_update_period).seconds.do(
        collect_rul_data,
        ser,
        online_device_indices,
        rul_newest_numbers,
        rul_collected_counts,
        data_folder,
        AQ_data_length,
        figs,
        axs_list,
    )
    schedule.every().hour.do(clear_terminal)


def run_scheduler_loop(ser, data_folder):
    """執行排程主迴圈。"""
    try:
        while True:
            schedule.run_pending()
            time.sleep(MAIN_LOOP_SLEEP_SEC)
    except KeyboardInterrupt:
        close_program(ser, status, chandle, " interrupted by user.", data_folder)


def prepare_runtime_context(ser):
    """建立本次執行所需的上下文（在線裝置、圖窗、檔案編號等）。"""
    online_device_indices = get_online_device_indices(ser)
    rul_newest_numbers = [1] * len(online_device_indices)
    rul_collected_counts = [0] * len(online_device_indices)

    if not online_device_indices:
        if DEBUG:
            print("No online devices found, entering debug mode...")
        else:
            print("No online devices found. Closing serial port.")
            input("按 Enter 鍵退出...")
            sys.exit()

    figs, axs_list = build_monitor_figures(online_device_indices)
    data_folder, rul_newest_numbers = check_and_create_folders(
        Motor_global_vars.Data_folder_path,
        online_device_indices,
        rul_newest_numbers,
    )

    return online_device_indices, rul_newest_numbers, rul_collected_counts, figs, axs_list, data_folder


def prepare_online_motors(ser, online_device_indices, figs, axs_list):
    """逐台執行開機前校正與預熱。"""
    for i in range(len(online_device_indices)):
        setup_motor_before_collection(ser, online_device_indices[i], figs[i], axs_list[i])


# ==================== 週期任務區 ====================

def collect_fast_data(ser, online_device_indices, Data_folder, AQ_data_length, figs,  axs_list):
    """FAST 週期任務：收集、估測、儲存 FAST 資料。"""
    with lock:

        if DEBUG:
            print("Collecting FAST data..., current time:", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
            return # Debugging
        for k, current_device_number in enumerate(online_device_indices):
            retries = 0
            while retries < MAX_RETRIES:
                if MOTOR_COND_FROM_IPC and FAST_in_IPC:
                    motor_cond, cond_err_sts = {}, False
                else:
                    # get motor operating condition from sensor packet
                    motor_cond, cond_err_sts = command_485.get_cond_pack(ser, current_device_number + 1, 3)
                # get motor fault status
                motor_cn_sts, cn_sts_err_sts = command_485.get_cn_pack(ser, current_device_number + 1, 3)
                if cond_err_sts or cn_sts_err_sts:
                    break # Skip this collection if condition flags are not received

                if not FAST_in_IPC:
                    # get FAST data (from AQbox)
                    unpack_fast_data, err_record, err_sts = command_485.get_all_FAST_pack(ser, current_device_number + 1, AQ_data_length)
                    torque_raw = None
                    v_alpha = v_beta = current_alpha_SI = current_beta_SI = flux_alpha_IPC = flux_beta_IPC = None
                    if MOTOR_COND_FROM_IPC:
                        # Build motor condition from IPC estimate even in FAST packet mode.
                        dataRUL_cond, _, cond_data_err = command_485.get_all_RUL_pack(ser, current_device_number + 1, AQ_data_length * 2)
                        if cond_data_err:
                            err_sts = True
                        else:
                            _, motor_cond, ipc_cond_err, _ = estimate_torque_and_motor_cond_from_rul_data(dataRUL_cond, motor_cond)
                            if ipc_cond_err:
                                err_sts = True

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
                    motor_cn_sts, fund_freq, minus1_freq=Data_handle_in_IPC.get_cn_sts_list(current_alpha_SI,current_beta_SI)
                    if MOTOR_COND_FROM_IPC:
                        speed_rpm = float(max(0.0, fund_freq * 60 / 2 / Motor_global_vars.Motor_P))
                        torque = float(np.mean(torque_raw[-Motor_global_vars.data_length:]))
                        power_kw = float(power_sts['Power_E'] / 1000)
                        motor_cond['speed'] = true_to_u16_data(speed_rpm, Motor_global_vars.Base_Speed)
                        motor_cond['torque'] = true_to_u16_data(torque, Motor_global_vars.Base_Torque)
                        motor_cond['power'] = true_to_u16_data(power_kw, Motor_global_vars.Base_Power)

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
                    if FAST_in_IPC and torque_raw is not None:
                        plot_sensory_data(figs[k], axs_list[k], v_alpha, v_beta, current_alpha_SI, current_beta_SI
                                          , flux_alpha_IPC, flux_beta_IPC, torque_raw)

                    break
                else:
                    retries += 1


def collect_rul_data(ser, online_device_indices, RUL_newest_numbers, RUL_collected_counts, Data_folder, AQ_data_length, figs, axs_list):
    """RUL 週期任務：收集、估測、儲存 RUL 資料並更新監控畫面。"""
    with lock:
        global status, chandle

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

            if MOTOR_COND_FROM_IPC:
                motor_cond, cond_err_sts = {}, False
            else:
                # get motor operating condition from sensor packet
                motor_cond, cond_err_sts = command_485.get_cond_pack(ser, current_device_number + 1, 3)

            while retries < MAX_RETRIES:
                time_now = time.time()
                # dataRUL, err_record, err_sts = command_485.get_all_RUL_pack(ser, current_device_number + 1, AQ_data_length * 4)
                dataRUL, err_record, err_sts = command_485.get_all_RUL_pack_bulk(ser, current_device_number + 1, AQ_data_length * 4)
                print(f'collect time:{time.time()-time_now}')
                torque_raw, motor_cond, ipc_cond_err, ipc_info = estimate_torque_and_motor_cond_from_rul_data(dataRUL, motor_cond)
                if MOTOR_COND_FROM_IPC and ipc_cond_err:
                    retries += 1
                    continue

                if not err_sts:
                    RUL_newest_numbers[j]=RUL_newest_numbers[j]+1
                    RUL_collected_counts[j] = RUL_collected_counts[j] + 1
                    Rul_folder_name = f"{Data_folder}/Update_data/RUL_data/RUL_{current_device_number + 1}"
                    CSV_file_name = f"{Rul_folder_name}/RUL_Data_{current_device_number + 1}_{RUL_newest_numbers[j]}.csv"
                   
                    # Data_handle.data_update_RUL_csv(ser, current_device_number + 1, CSV_file_name, dataRUL, retries=5, delay=1)
                    Data_handle.data_update_RUL_parquet(ser, current_device_number + 1, motor_cond,CSV_file_name, dataRUL
                                                        , retries=5, delay=1)  # save by parquet file


                    
                    # essemble_file_name = f"{Rul_folder_name}/RUL_Data_{current_device_number + 1}.h5"
                    # Data_handle.data_update_RUL_essemble(ser, current_device_number + 1, motor_cond,essemble_file_name, dataRUL
                    #                                     , retries=5, delay=1)  # save by essemble h5 file
                    
                    # print the collection  message
                    print(f'Device' + str(current_device_number+1) + ' RUL data ' + str(
                        RUL_newest_numbers[j]) + ' is saved, time:', time.strftime(" %H:%M:%S", time.localtime()))
                    if MOTOR_COND_FROM_IPC and ipc_info is not None:
                        print(
                            f"[IPC] torque={ipc_info['torque_nm']:.3f} Nm, "
                            f"power(E)={ipc_info['power_kw(E)']:.3f} KW, "
                            f"power(M)={ipc_info['power_kw(M)']:.3f} KW, "
                            f"speed={ipc_info['speed_rpm']:.3f} RPM, "
                            f"eff={ipc_info['efficiency_pct']:.2f}%"
                        )
                    plot_sensory_data_pico(figs[j], axs_list[j], dataRUL['voltage_alpha'], dataRUL['voltage_beta'],
                                           dataRUL['current_alpha'], dataRUL['current_beta'], torque_raw)

                    if RUL_collected_counts[j] >= Motor_global_vars.collection_times:
                        close_program(ser, status, chandle, f"reach the collection times {Motor_global_vars.collection_times}", Data_folder)
                    break
                else:
                    retries += 1

        # record the error times
        global total_err_count
        total_err_count = total_err_count + sum(err_record)

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


# ==================== 主流程區 ====================

def main():
    """主入口：初始化設備、執行前處理並啟動排程。"""
    print('AQbox data collection program start, version 1.0')

    # find and setups the AQbox port
    com = find_AQbox_port()
    ser = AQbox_serial_set_up(com)

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
            (
                online_device_indices,
                RUL_newest_numbers,
                RUL_collected_counts,
                figs,
                axs_list,
                Data_folder,
            ) = prepare_runtime_context(ser)

            # calibration CT offset and servo on the motors
            prepare_online_motors(ser, online_device_indices, figs, axs_list)
                
            print("All motors are ready, start data collection...")
            
            # run the first collection
            timenow = time.time()
            collect_rul_data(ser, online_device_indices, RUL_newest_numbers, RUL_collected_counts, Data_folder, AQ_data_length, figs, axs_list)
            
            print('rule collection run time: ', (time.time() - timenow))

            # 使用 schedule 定時執行
            schedule_collection_jobs(
                ser,
                online_device_indices,
                RUL_newest_numbers,
                RUL_collected_counts,
                Data_folder,
                figs,
                axs_list,
            )

            run_scheduler_loop(ser, Data_folder)

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
