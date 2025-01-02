import sys
import time
import serial
import command_485
import Data_handle
import os
import AQbox_simple_GUI
import Motor_global_vars

# parameter declairation
MAX_RETRIES=Motor_global_vars.max_tries # Max retry times in each collection cycle
AQ_PERIOD=Motor_global_vars.update_period #Basse data update period (1 min)
RUL_update_times = Motor_global_vars.RUL_update_times  # Actual RUL update time = RUL_update_times*AQ_PERIOD
AQ_data_length=Motor_global_vars.data_length # Signal length

# setup serial port

def find_AQbox_port():
    # 獲取所有可用的串口
    ports = serial.tools.list_ports.comports()

    for port in ports:
        if "Prolific PL2303GC" in port.description:
            return port.device
    print("No Prolific PL2303GC device found. Exiting program.")
    sys.exit()

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

COM=find_AQbox_port()
# COM = "COM9"
# COM = AQbox_simple_GUI.select_comport()
ser=AQbox_serial_set_up(COM)
print ('Serial Open success.')

try:
    ser.open()
except Exception as ex:
    print("open serial port error " + str(ex))
    exit()

if ser.is_open:
    # test codes
    # loss_time,err_time=0,0
    # for i in range(1, 4000):
    #     pkg_sts,data=command_485.get_one_4word_pack(ser, 1, 'FAST')
    #     loss_time = loss_time+ pkg_sts[0]
    #     err_time  = err_time + pkg_sts[1]
    # print(f'communication test loss time: {loss_time} error times: {err_time}')
    # command_485.reset_AQbox_FAST(ser,1)
    # check the device status
    device_status = command_485.check_device_number(ser, 0.05)
    online_devices = [index for index, value in enumerate(device_status) if value != 0]
    lines = [f"device {value+1} is online, data collect times: " for i, value in enumerate(online_devices)]
    online_device_indices = [index for index, value in enumerate(device_status) if value != 0]

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

    # Data collecting setting
    i=0
    N=10 # N is the data collecting times
    RUL_count = 1
    RUL_save_times = 0
    RUL_save=False
    # Data collecting start
    # while i<N:
    while 1: #loop forever
        # RUL collect determination
        RUL_save = RUL_count % RUL_update_times == 0
        if RUL_save:
            RUL_save_times += 1
        for j in range(len(online_device_indices)):
            current_device_number=online_device_indices[j]+1
            retries=0
            while retries < MAX_RETRIES:
                # collect data
                motor_cond, cond_err_sts=command_485.get_cond_pack(ser, current_device_number, 3)
                motor_cn_sts,cn_sts_err_sts=command_485.get_cn_pack(ser, current_device_number, 3)
                if cond_err_sts or cn_sts_err_sts: # if motor condition package fail too many times, skip this collection
                    print ('Motor condition get fail, skip this collection')
                    break
                unpack_fast_data, err_record, err_sts = command_485.get_all_FAST_pack(ser, current_device_number, AQ_data_length)
                if not err_sts:
                    # Update FAST data
                    CSV_file_name = './Update_data/FAST_data/' + 'Data_' + str(current_device_number) + '.csv'
                    Data_handle.data_update_FAST_csv(CSV_file_name, motor_cond, motor_cn_sts, unpack_fast_data,err_record, retries=3, delay=5)
                    # Data_handle.combine_ccae_sample(CSV_file_name)
                    print(f'FAST_data ' + str(current_device_number) + ' is updated')
                    if RUL_save:
                        # Update RUL data as the set period
                        RUL_retries=0
                        while RUL_retries < MAX_RETRIES:
                            dataRUL, err_record, err_sts = command_485.get_all_RUL_pack(ser, current_device_number,AQ_data_length*4)
                            if not err_sts: # collection fail
                                Rul_folder_name = './Update_data/RUL_data/RUL_' + str(current_device_number)
                                CSV_file_name = Rul_folder_name + '/RUL_Data_' + str(current_device_number) + '_' + str(
                                    RUL_save_times) + '.csv'
                                Data_handle.data_update_RUL_csv(ser, current_device_number, CSV_file_name, dataRUL, retries=5, delay=1)
                                print(f'RUL_data ' + str(current_device_number) + '_' + str(
                                    RUL_save_times) + ' is saved')
                                break
                            else:
                                RUL_retries += 1
                                if RUL_retries == MAX_RETRIES:
                                    print('RUL collection fail, skip this collection.')
                    break  # data collection success, jump up the loop
                else:
                    retries += 1
                    if retries == MAX_RETRIES:
                        print(f'FAST update fail, skip this collection.')
            time.sleep(1)# data transmission gap
        i+=1
        RUL_count=RUL_count+1
        time.sleep(AQ_PERIOD)  # data collection gap

    ser.close() # task complete, close the serial
else:
    print("Cannot open serial port")

    # for collecting progress display
    def display_progress(lines, collect_number):
        for i, task in enumerate(lines):
            sys.stdout.write(f"{lines[i]}{collect_number}\n")
        sys.stdout.flush()







