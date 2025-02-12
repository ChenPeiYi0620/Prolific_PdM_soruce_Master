import math
import struct
import csv
import os
import time
import numpy as np
import Motor_global_vars
import command_485
import pandas as pd


# save the RUL data into the parquet file with pandas dataframe
def data_update_RUL_parquet(ser, device_num, motor_cond, filename, unpack_rul_data, raw_pico_data, retries=5, delay=1):
    # rul data save status
    rul_data_is_save = 0
    # for motor online check
    current_raw_alpha = u16_to_true_data(np.array(unpack_rul_data['current_alpha']), 1)
    current_raw_beta = u16_to_true_data(np.array(unpack_rul_data['current_beta']), 1)
    current_raw_alpha_mean_rms = np.sqrt(np.mean((current_raw_alpha - np.mean(current_raw_alpha)) ** 2))
    motor_onine_flag = True  # for test only
    # motor_onine_flag = True if current_raw_alpha_mean_rms > 0.05 else False

    if motor_onine_flag:  # if motor is online, save the rul data
        voltage_alpha_out = u16_to_true_data(np.array(unpack_rul_data['voltage_alpha']), Motor_global_vars.Base_voltage)
        voltage_beta_out = u16_to_true_data(np.array(unpack_rul_data['voltage_beta']), Motor_global_vars.Base_voltage)
        # current_alpha_out = np.array(unpack_rul_data['current_alpha'])
        # current_beta_out  = np.array(unpack_rul_data['current_beta'])
        current_alpha_out = u16_to_true_data(np.array(unpack_rul_data['current_alpha']), Motor_global_vars.Base_current)
        current_beta_out = u16_to_true_data(np.array(unpack_rul_data['current_beta']), Motor_global_vars.Base_current)
        rul_out_data = np.vstack((voltage_alpha_out, voltage_beta_out, current_alpha_out, current_beta_out,
                                  np.array(unpack_rul_data['error_record'])))

        motor_cond_out_list = get_motor_cond_list(motor_cond)
        # conditions: 'Speed(Rpm)', 'Torque(N)', 'Power(KW)', 'Efficiency(%)', 'Efficiency_alarm'
        acc_rms = np.sqrt(np.mean((np.array(raw_pico_data) - np.mean(np.array(raw_pico_data))** 2)))
        data = {
            "Unix Time": [str(int(time.time()))],       # Unix 時間
            "Speed": [motor_cond_out_list[0]],          # 力矩 (Nm)
            "Torque": [motor_cond_out_list[1]],         # 效率 (%)
            "Power": [motor_cond_out_list[2]],          # 轉速 (RPM)
            "Efficiency": [motor_cond_out_list[3]],     # 功率 (W)
            "vibration rms":[acc_rms],
            "Voltage alpha": [voltage_alpha_out],
            "Voltage beta": [voltage_beta_out],
            "Current alpha": [current_alpha_out],
            "Current beta": [current_beta_out],
            "raw_pico_data":[raw_pico_data],
        }
        # create a DataFrame
        df_tosave = pd.DataFrame(data)

        # try to save the data
        for try_times in range(retries):
            try:
                base, ext = os.path.splitext(filename)  # 分離檔名與副檔名
                if ext.lower() == ".csv":
                     filename=base + ".parquet"
                df_tosave.to_parquet(filename, engine="pyarrow")
                rul_data_is_save = 1  # rul data save success
            except Exception as e:
                print(f'file saving error : {e}')
                print(f'{filename} open fail, try again {delay}s later ')
                time.sleep(delay)  # sleep for 5 second
    else:
        voltage_raw_alpha = u16_to_true_data(np.array(unpack_rul_data['voltage_alpha']), 1)
        voltage_raw_beta = u16_to_true_data(np.array(unpack_rul_data['voltage_beta']), 1)
        vac_alpha_offset = np.mean(voltage_raw_alpha)
        vac_beta_offset = np.mean(voltage_raw_beta)
        command_485.set_ct_offset(ser, device_num, delay=0.1, ct_offset_alpha=vac_alpha_offset,
                                  ct_offset_beta=vac_beta_offset, sensor='VAC')
        ct_alpha_offset = np.mean(current_raw_alpha)
        ct_beta_offset = np.mean(current_raw_beta)
        command_485.set_ct_offset(ser, device_num, delay=0.1, ct_offset_alpha=ct_alpha_offset,
                                  ct_offset_beta=ct_beta_offset, sensor='CT')

    return rul_data_is_save


# save the RUL data into the csv file
def data_update_RUL_csv (ser, device_num, file_path, unpack_rul_data, retries=5,delay=1):
    #rul data save status
    rul_data_is_save =0
    # for motor online check
    current_raw_alpha=u16_to_true_data(np.array(unpack_rul_data['current_alpha']), 1)
    current_raw_beta=u16_to_true_data(np.array(unpack_rul_data['current_beta']), 1)
    current_raw_alpha_mean_rms = np.sqrt(np.mean((current_raw_alpha-np.mean(current_raw_alpha)) ** 2))
    motor_onine_flag = True # for test only
    # motor_onine_flag = True if current_raw_alpha_mean_rms > 0.05 else False

    if motor_onine_flag: # if motor is online, save the rul data
        voltage_alpha_out = u16_to_true_data(np.array(unpack_rul_data['voltage_alpha']), Motor_global_vars.Base_voltage)
        voltage_beta_out  = u16_to_true_data(np.array(unpack_rul_data['voltage_beta']), Motor_global_vars.Base_voltage)
        # current_alpha_out = np.array(unpack_rul_data['current_alpha'])
        # current_beta_out  = np.array(unpack_rul_data['current_beta'])
        current_alpha_out = u16_to_true_data(np.array(unpack_rul_data['current_alpha']), Motor_global_vars.Base_current)
        current_beta_out  = u16_to_true_data(np.array(unpack_rul_data['current_beta']), Motor_global_vars.Base_current)
        rul_out_data = np.vstack((voltage_alpha_out, voltage_beta_out, current_alpha_out, current_beta_out, np.array(unpack_rul_data['error_record'])))

        for try_times in range(retries):
            try:
                # write to file
                # Organize data
                with open(file_path, mode='w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(['Unix_time',str(int(time.time()))])
                    writer.writerow(['V_alpha', 'V_beta', 'I_alpha', 'I_beta','error_flags'])
                    # 強制數值單位至小數點第六位
                    writer.writerows([[f"{x:.{6}f}" for x in row] for row in rul_out_data.T])
                rul_data_is_save=1 # rul data save success
            except Exception as e:
                print(f'file saving error : {e}')
                print(f'{file_path} open fail, try again {delay}s later ')
                time.sleep(delay)  # sleep for 5 second
    else:
        voltage_raw_alpha = u16_to_true_data(np.array(unpack_rul_data['voltage_alpha']), 1)
        voltage_raw_beta  = u16_to_true_data(np.array(unpack_rul_data['voltage_beta']), 1)
        vac_alpha_offset = np.mean(voltage_raw_alpha)
        vac_beta_offset = np.mean(voltage_raw_beta)
        command_485.set_ct_offset(ser, device_num, delay=0.1, ct_offset_alpha=vac_alpha_offset,
                                  ct_offset_beta=vac_beta_offset, sensor='VAC')
        ct_alpha_offset = np.mean(current_raw_alpha)
        ct_beta_offset = np.mean(current_raw_beta)
        command_485.set_ct_offset(ser, device_num, delay=0.1, ct_offset_alpha=ct_alpha_offset,
                                  ct_offset_beta=ct_beta_offset,sensor='CT')

    return rul_data_is_save
# save the FAST data into the csv file
def data_update_FAST_csv (file_path, motor_cond, motor_cn_sts, unpack_fast_data,err_record, retries=5,delay=1,device_number=1):
    ccae_data=read_sample_ccae()
    # Organize data
    motor_cond_out_list=get_motor_cond_list(motor_cond)
    motr_cn_sts_out_list=get_cn_sts_list(motor_cn_sts)
    # convert u16 data to floating point
    flux_alpha_out=u16_to_true_data( np.array(unpack_fast_data['flux_alpha']), 1)
    flux_beta_out =u16_to_true_data( np.array(unpack_fast_data['flux_beta']), 1)
    #  extend error record to flux data
    err_record=np.array(err_record)
    fast_out_data =np.vstack((flux_alpha_out, flux_beta_out,err_record))
    freqs, flux_fft_result = fft_test(flux_alpha_out, flux_beta_out, Motor_global_vars.sampling_rate)
    fast_out_data = np.vstack((freqs, flux_fft_result, flux_alpha_out, flux_beta_out, err_record, err_record))
    fast_out_data = fast_out_data.T
    Demag_status=get_demag_report(flux_alpha_out,flux_beta_out,flux_fft_result)

    for try_times in range(retries):
        try:
            # write to file
            with open(file_path, mode='w', newline='', encoding='utf-8') as csvfile:

                writer = csv.writer(csvfile)
                list0=pad_list_with_empty_strings(['Unix_time',str(int(time.time())),'Motor ID',Motor_global_vars.motor_id[device_number]])
                writer.writerow(pad_list_with_empty_strings(list0+['Zero_NG'],17))
                # Write state estimation result
                writer.writerow(pad_list_with_empty_strings(['Speed(Rpm)',	'Torque(N)',	'Power(KW)',	'Efficiency(%)',	'Efficiency_alarm'])+ccae_data[0])
                writer.writerow(pad_list_with_empty_strings(motor_cond_out_list)+ccae_data[1])
                # Write fault diagnosis result
                writer.writerow(pad_list_with_empty_strings(['Icn_x(A)', 'Icn_y(A)', 'CN_thres(%)',  'CN_alarm', 'CN_range(A)'])+ccae_data[2])
                writer.writerow(pad_list_with_empty_strings(motr_cn_sts_out_list)+ccae_data[3])
                writer.writerow(pad_list_with_empty_strings(['Flux_mag(mWb)', 'Flux_thd(pu)', 'Flux_thres(%)', 'Demag_alarm'])+ccae_data[4])
                writer.writerow(pad_list_with_empty_strings(Demag_status)+ccae_data[5])
                # Write RUL result
                rul_est=rul_result()
                writer.writerow(pad_list_with_empty_strings(['Health_Indicator', 'RUL_EN', 'RUL_alpha', 'RUL_beta','RUL_phi','RUL(min)','RUL_limit','t_N(min)'])+ccae_data[6])
                writer.writerow(pad_list_with_empty_strings(list(rul_est.values()))+ccae_data[7])
                writer.writerow(pad_list_with_empty_strings(['FFT_res(Hz)'])+ccae_data[8])
                writer.writerow(pad_list_with_empty_strings([Motor_global_vars.sampling_rate / Motor_global_vars.data_length])+ccae_data[9])
                # Write flux  signals
                writer.writerow( pad_list_with_empty_strings(['Flux_FFT_idx', 'FFT_result', 'Flux_x', 'Flux_y', 'Rul_t(HR) ', 'RUL_curve'])+ccae_data[10])
                for row_index in range(fast_out_data.shape[0]):
                    flux_datarow = pad_list_with_empty_strings(list(fast_out_data[row_index, :]),8)
                    if row_index<21-10:
                        flux_datarow=flux_datarow+ccae_data[row_index+10+1]
                    pad_list_with_empty_strings(flux_datarow,17)
                    # for row in flux_datarow:
                    #     formatted_row = [
                    #         f"{value:.{precision}f}" if isinstance(value, float) else value
                    #         for value in row
                    #     ]
                    writer.writerow(flux_datarow)
        except Exception as e:
            print(f'data saving error: {e}')
            print(f'{file_path} open fail, try again {delay}s later ')
            time.sleep(delay) # sleep for 5 second
# rul result operation (still developing)
def rul_result():
    # use dictionary to storage RUL result
    rul_est={'Health_Indicator':0,'RUL_EN':0,'RUL_alpha':0,
             'RUL_beta':0,'RUL_phi':0,'RUL(min)':0,'RUL_limit':0,'t_N(min)':0}
    return rul_est
# simple fft calculation
def fft_test(signal_real,signal_imag,sampling_rate):
    T = 1 / sampling_rate
    N = len(signal_real)
    freqs = np.fft.fftfreq(N, T)
    freqs = np.fft.fftshift(freqs)
    real_part = np.array(signal_real)
    imaginary_part = np.array(signal_imag)
    complex_array = real_part + 1j * imaginary_part
    fft_result = np.fft.fft(complex_array)
    fft_result=np.fft.fftshift(fft_result/len(fft_result))
    return freqs, np.abs(fft_result)
# get motor operating condition
def get_motor_cond_list(motor_cond_raw):
    # conditions: 'Speed(Rpm)', 'Torque(N)', 'Power(KW)', 'Efficiency(%)', 'Efficiency_alarm'
    motr_cond_list=[]
    motr_cond_list.append(u16_to_true_data(motor_cond_raw['speed'],pu_gain=Motor_global_vars.Base_Speed))
    motr_cond_list.append(u16_to_true_data(motor_cond_raw['torque'], pu_gain=Motor_global_vars.Base_Torque))
    motr_cond_list.append(u16_to_true_data(motor_cond_raw['power'], pu_gain=Motor_global_vars.Base_Power))
    # power is offset by 0.00001 to avoid divide by zero
    motr_cond_list.append((motr_cond_list[0]/60*2*math.pi* motr_cond_list[1]/(motr_cond_list[2]+0.000001) *100))
    # motr_cond_list.append((max((motr_cond_list[0]*4/60*2*math.pi* motr_cond_list[1]/(motr_cond_list[2]+0.000001) *100/1000),96.1)))
    motr_cond_list.append(int(motr_cond_list[3]<90))
    return motr_cond_list
# get cn diagnosis result
def get_cn_sts_list(motor_cn_raw):
    # conditions: 'Speed(Rpm)', 'Torque(N)', 'Power(KW)', 'Efficiency(%)', 'Efficiency_alarm'
    motor_cn_list=[]
    cn_base=u16_to_true_data(motor_cn_raw['I_rms'], pu_gain=Motor_global_vars.Base_current)
    cn_range=cn_base*Motor_global_vars.cn_range_scale
    motor_cn_list.append(u16_to_true_data(motor_cn_raw['Icn_x'], pu_gain=Motor_global_vars.Base_current))
    motor_cn_list.append(u16_to_true_data(motor_cn_raw['Icn_y'], pu_gain=Motor_global_vars.Base_current))
    cn_thres=math.sqrt(motor_cn_list[0]**2+motor_cn_list[1]**2)/cn_base*100
    motor_cn_list.append(cn_thres)
    motor_cn_list.append(int(motor_cn_list[2]>100))
    motor_cn_list.append(cn_range)
    return motor_cn_list
# rescale the Uint16 data to float
def u16_to_true_data(u16_data, pu_gain=1):
    float_data=(u16_data-32768)/32768*pu_gain
    return float_data
# read the smple ccae result for ui test
def read_sample_ccae():
    file_path = "CCAE_sample.csv"
    ccae_dict = {}
    with open(file_path, mode='r', newline='', encoding='utf-8') as file:
        reader = csv.reader(file)
        for index, row in enumerate(reader):
            ccae_dict[index] = row  # 保留整行數據，包括字串和數字
    return ccae_dict
# padding function to write specific format of data file
def pad_list_with_empty_strings(input_list, target_length=8):
   # if list length<target_length, pad it
    if len(input_list) < target_length:
        input_list.extend([""] * (target_length - len(input_list)))
    return input_list
# generate demagnetization report from raw flux data
def get_demag_report(flux_alpha, flux_beta, flux_fft):
    pm_strength= np.average(np.sqrt(flux_alpha**2 + flux_beta**2))
    pm_thres= min( pm_strength/Motor_global_vars.Base_flux,1)*100
    flux_thd=calculate_thd_with_fftshift(flux_fft)
    pm_alarm= int(pm_thres<90)
    demag_status=[pm_strength, pm_thres, flux_thd, pm_alarm]
    return demag_status
# calculate thd of flux fft (need to check )
def calculate_thd_with_fftshift(fft_complex):
    """
    計算經 fftshift 處理後的 FFT 頻譜的 THD（總諧波失真）。

    Parameters:
        fft_complex (np.ndarray): 經 fftshift 的複數 FFT 頻譜數據。

    Returns:
        thd (float): THD 值（單位：百分比）。
    """
    # 1. 反向 fftshift 將頻譜恢復為未移位狀態
    fft_complex = np.fft.ifftshift(fft_complex)

    # 2. 計算幅值譜，忽略 DC 分量
    fft_magnitude = np.abs(fft_complex)
    fft_magnitude[0] = 0  # 忽略 DC 分量

    # 3. 找到基波的索引（最大幅值）
    fundamental_index = np.argmax(fft_magnitude)
    V1 = fft_magnitude[fundamental_index]  # 基波幅值

    # 4. 計算諧波總和（排除基波）
    fft_magnitude[fundamental_index] = 0  # 忽略基波
    harmonic_power = np.sum(fft_magnitude ** 2)

    # 5. 計算 THD
    thd = np.sqrt(harmonic_power) / V1   # 轉換為百分比

    return thd






