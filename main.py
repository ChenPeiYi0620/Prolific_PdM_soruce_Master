import sys
import time
import serial

import command_485
import command_485 as cmd485
import Data_handle as d_handle
import os
import AQbox_simple_GUI
import Motor_global_vars as m_vars
import rul_pico_functions as r_pico
import numpy as np
import schedule
import threading

# create lock
lock = threading.Lock()

# parameter declairation
MAX_RETRIES=m_vars.max_tries # Max retry times in each collection cycle
AQ_PERIOD=m_vars.update_period #Basse data update period (1 min)
RUL_update_times = m_vars.RUL_update_times  # Actual RUL update time = RUL_update_times*AQ_PERIOD
AQ_data_length=m_vars.data_length # Signal length
RUL_save_times=1 # RUL save count
acc_alarm_count=0 # vibration alarm trigger times


# for collecting progress display
def stop_all(ser,status, chandle, stop_reason):
    ser.close()
    r_pico.pico_close(status, chandle)
    sys.exit(stop_reason)

def display_progress(lines, collect_number):
    for i, task in enumerate(lines):
        sys.stdout.write(f"{lines[i]}{collect_number}\n")
    sys.stdout.flush()
# find_AQbox_port is used to automatically find comport number of PLC303
def find_AQbox_port():
    # 獲取所有可用的串口
    ports = serial.tools.list_ports.comports()

    for port in ports:
        if "Prolific PL2303GC" in port.description:
            return port.device
    print("No Prolific PL2303GC device found. Exiting program.")
    sys.exit()
# AQbox_serial_set_up is use to setup pyserial with specific comport number
def AQbox_serial_set_up(COM):
    # initialize the serial port
    ser = serial.Serial()
    ser.port = COM
    ser.baudrate = 921600
    ser.bytesize = serial.EIGHTBITS  # number of bits per bytes
    ser.parity = serial.PARITY_NONE  # set parity check
    ser.stopbits = serial.STOPBITS_TWO  # number of stop bits

    ser.timeout = 0.1  # non-block read sms
    ser.writeTimeout = 0.05  # timeout for write 0.5s
    ser.xonxoff = False  # disable software flow control
    ser.rtscts = False  # disable hardware (RTS/CTS) flow control
    ser.dsrdtr = False  # disable hardware (DSR/DTR) flow control
    return ser
# scheduling task1: motor status check
def motor_status_check(ser,online_device_indices):
        global status, chandle, runblock_settings,chARange
        with lock:
            for i in range(len(online_device_indices)):
                current_device_number=online_device_indices[i] + 1
                # check the connection, if fail then stop program
                if cmd485.reset_AQbox_FAST(ser,current_device_number)==1:
                    command_485.servo_control(current_device_number, ser, 1)
                    stop_all(ser,status, chandle, 'Connection fail.')
                # run the pico block to check acc level
                r_pico.runblock_pico_A(status, chandle, runblock_settings)
                # ge pico acc data and its rms
                chARange, pico_data = r_pico.get_pico_values(status, chandle, runblock_settings, chARange)
                acc_rms = np.sqrt(np.mean((pico_data - np.mean(pico_data)) ** 2))
                # print(f'Current acc rms of device {current_device_number} is : {acc_rms:.5f}')
                if acc_rms>m_vars.acc_threshold:
                    global acc_alarm_count #stop collection if vibration alarm trigger too many times
                    acc_alarm_count=acc_alarm_count+1 if acc_alarm_count>5 else stop_all(ser, status, chandle, f'Vibration alarm{acc_rms:.5f}' )

# scheduling task1: rul data collection
def motor_rul_collect(ser, online_device_indices):
    global RUL_save_times, status, chandle, runblock_settings, chARange
    with lock:
        for j in range(len(online_device_indices)):
            current_device_number = online_device_indices[j] + 1
            RUL_retries = 0
            # run the pico block
            r_pico.runblock_pico_A(status, chandle, runblock_settings)
            while RUL_retries < MAX_RETRIES:
                dataRUL, err_record, err_sts = cmd485.get_all_RUL_pack(ser, current_device_number,
                                                                       AQ_data_length * 4)
                # ge pico acc data and its rms
                chARange, pico_data = r_pico.get_pico_values(status, chandle, runblock_settings, chARange)
                acc_rms = np.sqrt(np.mean((pico_data - np.mean(pico_data)) ** 2))
                if not err_sts:  # collection success
                    Rul_folder_name = './Update_data/RUL_data/RUL_' + str(current_device_number)
                    CSV_file_name = Rul_folder_name + '/RUL_Data_' + str(current_device_number) + '_' + str(
                        RUL_save_times) + '.csv'
                    d_handle.data_update_RUL_csv(ser, current_device_number, CSV_file_name, dataRUL, retries=5,
                                                 delay=1, acc_data=pico_data)
                    print(f'RUL_data ' + str(current_device_number) + '_' + str(
                        RUL_save_times) + f' is saved, acc_rms={acc_rms}')
                    RUL_save_times = RUL_save_times + 1
                    break
                else:
                    RUL_retries += 1
                    if RUL_retries == MAX_RETRIES:
                        print('RUL collection fail too many times , stop collection.')
                        command_485.servo_control(current_device_number, ser, 0)
                time.sleep(1)  # data transmission gap
# shcduling
def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

# setup serial port
COM=find_AQbox_port()
ser=AQbox_serial_set_up(COM)
print ('Serial Open success.')

#setup pico device
status, chandle, runblock_settings, chARange = r_pico.pico_setup_acc(AQ_data_length*4)

# try  open serial
try:
    ser.open()
except Exception as ex:
    print("open serial port error " + str(ex))
    exit()

if ser.is_open:
    # test codes
    # loss_time,err_time=0,0
    # for i in range(1, 4000):
    #     pkg_sts,data=cmd485.get_one_4word_pack(ser, 1, 'FAST')
    #     loss_time = loss_time+ pkg_sts[0]
    #     err_time  = err_time + pkg_sts[1]
    # print(f'communication test loss time: {loss_time} error times: {err_time}')
    # cmd485.reset_AQbox_FAST(ser,1)
    # check the device status
    device_status = cmd485.check_device_number(ser, 0.05)
    online_devices = [index for index, value in enumerate(device_status) if value != 0]
    lines = [f"device {value+1} is online, data collect times: " for i, value in enumerate(online_devices)]
    online_device_indices = [index for index, value in enumerate(device_status) if value != 0]

    # servo on the motors
    for i in range(len(online_device_indices)):
        command_485.servo_control(online_device_indices[i]+1,ser,1)

    #  prepare the data folder
    if not os.path.exists('./Update_data/FAST_data'):
        # is folder not exist
        os.makedirs('./Update_data/FAST_data')
    for i in range(len(online_device_indices)):
        Rul_folder_name = './Update_data/RUL_data/RUL_' + str(online_device_indices[i] + 1)
        if not os.path.exists(Rul_folder_name):
            # if folder not exist
            os.makedirs(Rul_folder_name)

    if not online_devices:
        ser.close()
        sys.exit("No device is online")

    # scheduling
    schedule.every(3).seconds.do(lambda:motor_status_check(ser,online_device_indices))
    schedule.every(5).seconds.do(lambda:motor_rul_collect(ser, online_device_indices))

    # run schedule
    thread = threading.Thread(target=run_schedule)
    thread.start()


    # # Data collecting setting
    # i=0
    # N=10 # N is the data collecting times
    # RUL_count = 1
    # RUL_save_times = 0
    # RUL_save=False
    # # Data collecting start (with threading)
    #
    # # while i<N:
    # while 1: #loop forever
    #     for j in range(len(online_device_indices)):
    #         current_device_number=online_device_indices[j]+1
    #         RUL_retries=0
    #         # run the pico block
    #         r_pico.runblock_pico_A(status, chandle, runblock_settings)
    #         while RUL_retries < MAX_RETRIES:
    #             dataRUL, err_record, err_sts = cmd485.get_all_RUL_pack(ser, current_device_number,
    #                                                                    AQ_data_length * 4)
    #             # ge pico acc data and its rms
    #             chARange, pico_data = r_pico.get_pico_values(status, chandle, runblock_settings, chARange)
    #             acc_rms = np.sqrt(np.mean((pico_data - np.mean(pico_data)) ** 2))
    #             if not err_sts:  # collection success
    #                 Rul_folder_name = './Update_data/RUL_data/RUL_' + str(current_device_number)
    #                 CSV_file_name = Rul_folder_name + '/RUL_Data_' + str(current_device_number) + '_' + str(
    #                     RUL_save_times) + '.csv'
    #                 d_handle.data_update_RUL_csv(ser, current_device_number, CSV_file_name, dataRUL, retries=5,
    #                                              delay=1, acc_data=pico_data)
    #                 print(f'RUL_data ' + str(current_device_number) + '_' + str(
    #                     RUL_save_times) + f' is saved, acc_rms={acc_rms}')
    #                 break
    #             else:
    #                 RUL_retries += 1
    #                 if RUL_retries == MAX_RETRIES:
    #                     print('RUL collection fail too many times , stop collection.')
    #                     command_485.servo_control(current_device_number, ser, 0)
    #             RUL_save_times=RUL_save_times+1
    #             time.sleep(1)# data transmission gap
    #     i+=1
    #     RUL_count=RUL_count+1
    #     time.sleep(AQ_PERIOD)  # data collection gap
    # # task complete, close the serial port and pico device
    # ser.close()
    # pico_close(status, chandle)
else:
    print("Cannot open serial port")







