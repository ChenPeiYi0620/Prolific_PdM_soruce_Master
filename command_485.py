import time
import struct
import numpy as np
import serial
# import matplotlib.pyplot as plt
import Motor_global_vars

def read_status(ser,device_num,delay=0.1):
    # clear_RFIFO_buffer(ser)
    device_status=0
    v_mode=0 if Motor_global_vars.V_measure_mode=='Vpwm_mode' else 1
    cmd=[1, device_num, 1, 0]+[v_mode]
    byte_cmd = bytes(cmd)
    ser.write(byte_cmd)
    ser.flush()  # flush output buffer
    data = ser.read(4)  # read all buffer data or wait for one byte data
    time.sleep(delay)
    ser.flushInput()  # flush input buffer
    if data:  # if device is online, a int 5 will be response
        data1=data[0]
        crc = device_num + data[2]
        if crc == 255 : # check parameter setup result
            for i in range(3): # try 3 times at max
                set_status=set_device_para(ser, device_num, delay=0.5, Rs=Motor_global_vars.Motor_Rs,
                                           Ls=Motor_global_vars.Motor_Ls, P=Motor_global_vars.Motor_P,
                                           CT_gain=Motor_global_vars.Base_current)
                if  set_status:
                    device_status=1
                    print(f" Device {device_num} is online.")
                    return device_status
            print(f" Device {device_num} set parameter fail.")
            return device_status
        else:
            print(f" Device {device_num} has incorrect response. {data}")
            return device_status
    else :
        pass
        # print(f" Device {device_num} is not connect.")

        return device_status

def check_device_number(ser, delay=0.1):
    device_number = 8  # 16 device at max
    device_status = [0] * device_number
    try:
        for i in range(1, device_number+1):
            sts= read_status(ser, i, delay)
            device_status[i - 1] = sts  # if device is on, set the status to 1
    except serial.SerialException as ex:
        print(f"Serial error occurred: {ex}")
    except Exception as ex:
        print(f"An error occurred: {ex}")
    finally:
        pass
    return device_status

def set_device_para(ser,device_num,delay=0.1,Rs=3.3,Ls=0.1,P=8, CT_gain=184.668):

    Rs_bytes_data = list(struct.pack('<f', Rs))
    Ls_bytes_data = list(struct.pack('<f', Ls))
    CT_gain_bytes_data = list(struct.pack('<f', CT_gain))


    set_status=0

    cmd = [1, device_num, 6]+Rs_bytes_data+Ls_bytes_data+CT_gain_bytes_data+[P]

    byte_cmd = bytes(cmd)
    ser.write(byte_cmd)
    ser.flush()  # flush output buffer
    time.sleep(delay)
    data = ser.read(15)  # read all buffer data or wait for one byte data
    ser.flushInput()  # flush input buffer
    if data:  # if device is online, a int 5 will be response
        if not(len(data)==15): #length incorrect
            return set_status
        data_eco = list(data)
        data_eco=data_eco[1:]
        cmd_check=cmd[3:]
        cmd_check.insert(0, device_num)
        if (cmd_check==data_eco):
            set_status=1 # parameter set success
            return set_status
        else:
            return set_status
    else:
        return set_status

# get the raw current, voltage and flux estimation data
def get_device_data(ser, device_number, data_length):
    data_length_code=0
    if data_length % 2000 != 0:
        print("Illegal data_length")
    else:
        data_length_code = int(data_length / 2000 - 1)
        try:
            ser.flush()  # flush input buffer
            ser.write(bytes([1, device_number,2, data_length_code]))  # command code 2 represent data collecting
            data = read_large_data_with_timeout(ser)
            # total data_length*2*4(signal number)+2(crc) bytes
            if data:
                print(f" Device {device_number} Data collection complete")  # 解碼並打印數據
                return data
        except serial.SerialException as ex:
            print(f"Serial error occurred: {ex}")
        except Exception as ex:
            print(f"An error occurred: {ex}")
        finally:
            pass

def read_large_data_with_timeout(ser):
    data = bytearray()
    while True:
        chunk = ser.read(1024)  # read 1024 byte each time
        if not chunk:  # time_out or has no more data
            break
        data.extend(chunk)
    return data

# get one data pack (4 word sensor data)
def get_one_4word_pack(ser, device_num, Master_cmd):
    if  Master_cmd=='RUL':
        Master_cmd=4
    elif Master_cmd=='FAST':
        Master_cmd=3
    elif Master_cmd=='Cond':
        Master_cmd=2
    else:
        Master_cmd = 7
    cmd = [1, device_num, Master_cmd, 0] #2 is for RUL data
    byte_cmd = bytes(cmd)
    pack_status=[0,0] # package collect status, first means pksg loss, second means data err
    try:
        ser.reset_input_buffer()
        ser.write(byte_cmd)
        ser.flush()  # ensure sending is complete
        # data = ser.read(ser.in_waiting or 10)  # read all buffer data or wait for one byte data
        data = ser.read(10)
        if len(data)==10:
            if not (data[0] == 0x2 and data[1] == device_num):
                pack_status=[0,1]
            return pack_status, data
        else:

            if len(data)==0:
                data = bytearray(10)  # fake data
                return [1, 0], data
            else:
                # print(f"incorrect data length: {len(data)}, data: {data.hex()}")
                data = bytearray(10)  # fake data
                return [0, 1], data # incorrect data length
    except Exception as ex:
        print(f"FAST data collect incomplete")
        data= bytearray(10)
        return [1,1], data
    finally:
        pass

# get motor condition
def get_cond_pack(ser, device_num,MAX_retries):
    # get motor condition
    i, pkg_sts, data, raw_motor_cond = 0, [0,0], 0,0
    while i < MAX_retries:
        pkg_sts, data = get_one_4word_pack(ser, device_num, 'Cond')
        if not (pkg_sts[0] + pkg_sts[1]):  # if success
            break
        else:
            i = i + 1
    raw_motor_cond = struct.unpack("5H", data)
    motor_cond = {
        'speed':  raw_motor_cond[1],
        'torque': raw_motor_cond[2],
        'power':  raw_motor_cond[3],
    }
    collect_sts=min(pkg_sts[0] + pkg_sts[1],1)
    return motor_cond,collect_sts
# get motor cn fault status
def get_cn_pack(ser, device_num,MAX_retries):
    # get motor condition
    i, pkg_sts, data, raw_motor_cn_sts = 0, [0,0], 0,0
    while i < MAX_retries:
        pkg_sts, data = get_one_4word_pack(ser, device_num, 'Cn')
        if not (pkg_sts[0] + pkg_sts[1]):  # if success
            break
        else:
            i = i + 1
    raw_motor_cn_sts = struct.unpack("5H", data)
    motor_cn_sts = {
        'Icn_x':  raw_motor_cn_sts[1],
        'Icn_y':  raw_motor_cn_sts[2],
        'I_rms':  raw_motor_cn_sts[3],
    }
    collect_sts=min(pkg_sts[0] + pkg_sts[1],1)
    return motor_cn_sts,collect_sts

# get Flux data pack by pack
def get_all_FAST_pack(ser, device_num,data_length):
    # FAST_data = [[0] * data_length for _ in range(4)]
    FAST_data, FAST_data1, FAST_data2, FAST_data3, err_flags = [[0] * data_length for _ in range(5)]
    err_count_loss =0 # package loss times
    err_count_err = 0  # package error times
    collect_sts=0  #transmit status
    last_int16_values = [0] * 5  # to handle package error
    for i in range(1, data_length+1) :
        # pkg_sts,data=get_one_FAST_pack(ser, device_num)
        pkg_sts,data=get_one_4word_pack(ser, device_num, 'FAST')
        # replace data with previous one if error
        if (pkg_sts[0]+pkg_sts[1])>0:
            int16_values = last_int16_values
            err_count_loss = err_count_loss + pkg_sts[0]
            err_count_err = err_count_err + pkg_sts[1]
            err_flags[i - 1] = 1
        else:
            int16_values = struct.unpack("5H", data)
        last_int16_values = int16_values # update last data
        FAST_data[i-1]   = int16_values[1]
        FAST_data1[i - 1] = int16_values[2]
        FAST_data2[i - 1] = int16_values[3] # idle
        FAST_data3[i - 1] = int16_values[4] # idle
        err_flags [i - 1] = 0
        if (err_count_loss+err_count_err)>=100:
            print("Collection fail too many times, end this collection")
            collect_sts=1
            break #transmition fail too many times, terminate this collection
    reset_AQbox_FAST(ser, device_num)
    print(f"\rPackage　loss: {err_count_loss} error: {err_count_err}", end=" ")
    FAST_total = {
        'flux_alpha': FAST_data,
        'flux_beta': FAST_data1,
        'error_record': err_flags
    }
    return FAST_total,err_flags,collect_sts
# get RUL data pack by pack
def get_all_RUL_pack(ser, device_num,data_length):
    # FAST_data = [[0] * data_length for _ in range(4)]
    RUL_data  = [0] * data_length
    RUL_data1 = [0] * data_length
    RUL_data2 = [0] * data_length
    RUL_data3 = [0] * data_length
    err_flags  = [0] * data_length # transmit error record
    err_count_loss = 0  # package loss times
    err_count_err = 0  # package error times
    collect_sts=0  #transmit status
    last_int16_values=[0]*5 # to handle package error
    for i in range(1, data_length+1) :
        # time.sleep(0.001)
        # pkg_sts,data=get_one_RUL_pack(ser, device_num)
        pkg_sts, data = get_one_4word_pack(ser, device_num, 'RUL')
        # replace data with previous one if error
        if (pkg_sts[0]+pkg_sts[1])>0:
            int16_values = last_int16_values
            err_count_loss = err_count_loss + pkg_sts[0]
            err_count_err = err_count_err + pkg_sts[1]
            err_flags[i - 1] = 1
        else :
            int16_values = struct.unpack("5H", data)
        last_int16_values=int16_values
        # data update
        RUL_data[i-1]   = int16_values[1]
        RUL_data1[i - 1] = int16_values[2]
        RUL_data2[i - 1] = int16_values[3]
        RUL_data3[i - 1] = int16_values[4]
        err_flags [i - 1] = 0
        if (err_count_loss+err_count_err)>=100:
            print("Collection fail too many times, skip this collection")
            collect_sts=1
            break #transmition fail too many times, terminate this collection
    reset_AQbox_FAST(ser, device_num)
    print(f"Package　loss: {err_count_loss} error: {err_count_err}", end=", ")
    RUL_total= {
        'voltage_alpha':    RUL_data,
        'voltage_beta':     RUL_data1,
        'current_alpha':    RUL_data2,
        'current_beta':     RUL_data3,
        'error_record':     err_flags
    }
    return RUL_total,err_flags,collect_sts

# invalid command, force AQbox to read out the data buffer
def clear_RFIFO_buffer(ser):
    ser.write([0, 0, 0, 0])
    ser.flush()  # flush output buffer

# Update CT and Vac offset when offline
def set_ct_offset(ser,device_num,delay=0.1,ct_offset_alpha=0, ct_offset_beta=0, sensor='CT'):
    ct_offset_as=ct_offset_alpha
    ct_offset_bs=(1.73205080757*ct_offset_beta-ct_offset_alpha)/2 # inverse Clarke
    ct_offset_as_bytes_data = list(struct.pack('<f', ct_offset_as))
    ct_offset_bs_bytes_data = list(struct.pack('<f', ct_offset_bs))
    if sensor=='CT':
        cmd = [1, device_num, 8]+ct_offset_as_bytes_data+ct_offset_bs_bytes_data
    else :
        cmd = [1, device_num, 9] + ct_offset_as_bytes_data + ct_offset_bs_bytes_data
    byte_cmd = bytes(cmd)
    ser.write(byte_cmd)
    ser.flush()  # flush output buffer
    time.sleep(delay)
    data = ser.read(15)  # read all buffer data or wait for one byte data
    ser.flushInput()  # flush input buffer
    if data:  # if device is online, a int 5 will be response
        if not(len(data)==10): #length incorrect
            print(f'{sensor} offset calibration fail ')
        data_eco = list(data)
        data_eco=data_eco[1:]
        cmd_check=cmd[3:]
        cmd_check.insert(0, device_num)
        if (cmd_check==data_eco):
            pass
            # print(f'{sensor} offset calibration success, offset as: {sensor}_offset_as: {ct_offset_as}, bs: {ct_offset_bs}')
        else:
            print(f'{sensor} offset calibration fail ')
    else:
        print(f'{sensor} offset calibration fail ')

def set_vac_offset(ser,device_num,delay=0.1,ct_offset_alpha=0, ct_offset_beta=0):
    ct_offset_as=ct_offset_alpha
    ct_offset_bs=(1.73205080757*ct_offset_beta-ct_offset_alpha)/2 # inverse Clarke
    ct_offset_as_bytes_data = list(struct.pack('<f', ct_offset_as))
    ct_offset_bs_bytes_data = list(struct.pack('<f', ct_offset_bs))

    cmd = [1, device_num, 8]+ct_offset_as_bytes_data+ct_offset_bs_bytes_data

    byte_cmd = bytes(cmd)
    ser.write(byte_cmd)
    ser.flush()  # flush output buffer
    time.sleep(delay)
    data = ser.read(15)  # read all buffer data or wait for one byte data
    ser.flushInput()  # flush input buffer
    if data:  # if device is online, a int 5 will be response
        if not(len(data)==10): #length incorrect
            print('CT offset calibration fail ')
        data_eco = list(data)
        data_eco=data_eco[1:]
        cmd_check=cmd[3:]
        cmd_check.insert(0, device_num)
        if (cmd_check==data_eco):
            print(f'CT offset calibration success, offset as: ct_offset_as{ct_offset_as}, bs: {ct_offset_bs}')
        else:
            print('CT offset calibration fail ')
    else:
        print('CT offset calibration fail ')


# enable AQbox to update data buffer
def reset_AQbox_FAST(ser,device_num):
    reset_status=1
    for i in range(3):  # try 3 times at max
        ser.write([1, device_num, 5, 0])
        ser.flush()  # flush output buffer
        data = ser.read(4)  # read all buffer data or wait for one byte data
        ser.flushInput()  # flush input buffer
        if data:  # if device is online, a int 5 will be response
            crc = device_num + data[2]
            if crc == 255:
                reset_status=0
                break
    if reset_status==1:
        print('reset fail')
    return reset_status

# cmd 10: servo control
def servo_control(device_num, ser, servo_on):
    servo_status=0 #servo_status=0 if set succeed
    # sevo turns on if servo_on=1, otherwise turn off
    cmd = [1, device_num, 10]+[servo_on]
    byte_cmd = bytes(cmd)
    try_time=0
    while try_time<3:
        ser.write(byte_cmd)
        ser.flush()  # flush output buffer
        data = ser.read(4)  # read all buffer data or wait for one byte data
        ser.flushInput()  # flush input buffer
        if data and (device_num + data[2])==255:  # if device is online, a int 5 will be response
            print('servo on set complete') if servo_on==1 else  print('servo off set complete')
            time.sleep(2) # wait the motor start
            break
        try_time=try_time+1
    if servo_status:
        print('servo control fail, stop collection')
        exit()
    return


# def simple_plot(data_list):
#      plt.plot(data_list)  # 使用圓圈標記節點
#      plt.title("Simple List Plot")  # 設置標題
#      plt.xlabel("Index")  # x 軸標籤
#      plt.ylabel("Value")  # y 軸標籤
#      plt.grid(True)  # 添加網格線
#      plt.show(block=False)
