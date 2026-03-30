# This program do the same thing as Data handle but the motor status is calculated in here

import math
import csv
import pandas as pd
import time
import numpy as np
import matplotlib.pyplot as plt
import Motor_global_vars
import command_485


# save the RUL data into the csv file
def data_update_RUL_csv(ser, device_num, file_path, unpack_rul_data, retries=5, delay=1):
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

        for try_times in range(retries):
            try:
                # write to file
                # Organize data
                with open(file_path, mode='w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(['Unix_time', str(int(time.time()))])
                    writer.writerow(['V_alpha', 'V_beta', 'I_alpha', 'I_beta', 'error_flags'])
                    # 強制數值單位至小數點第六位
                    writer.writerows([[f"{x:.{6}f}" for x in row] for row in rul_out_data.T])
                rul_data_is_save = 1  # rul data save success
            except Exception as e:
                print(f'file saving error : {e}')
                print(f'{file_path} open fail, try again {delay}s later ')
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


# save the FAST data into the csv file
def data_update_FAST_csv(file_path, motor_cond, motor_cn_sts, unpack_fast_data, err_record, retries=5, delay=1,
                         device_number=1):
    ccae_data = read_sample_ccae()
    # Organize data
    motor_cond_out_list = get_motor_cond_list(motor_cond)
    motr_cn_sts_out_list = get_cn_sts_list(motor_cn_sts)
    # convert u16 data to floating point
    flux_alpha_out = u16_to_true_data(np.array(unpack_fast_data['flux_alpha']), 1)
    flux_beta_out = u16_to_true_data(np.array(unpack_fast_data['flux_beta']), 1)
    #  extend error record to flux data
    err_record = np.array(err_record)
    fast_out_data = np.vstack((flux_alpha_out, flux_beta_out, err_record))
    freqs, flux_fft_result = fft_test(flux_alpha_out, flux_beta_out, Motor_global_vars.sampling_rate)
    fast_out_data = np.vstack((freqs, flux_fft_result, flux_alpha_out, flux_beta_out, err_record, err_record))
    fast_out_data = fast_out_data.T
    Demag_status = get_demag_report(flux_alpha_out, flux_beta_out, flux_fft_result)

    for try_times in range(retries):
        try:
            # write to file
            with open(file_path, mode='w', newline='', encoding='utf-8') as csvfile:

                writer = csv.writer(csvfile)
                list0 = pad_list_with_empty_strings(
                    ['Unix_time', str(int(time.time())), 'Motor ID', Motor_global_vars.motor_id[device_number]])
                writer.writerow(pad_list_with_empty_strings(list0 + ['Zero_NG'], 17))
                # Write state estimation result
                writer.writerow(pad_list_with_empty_strings(
                    ['Speed(Rpm)', 'Torque(N)', 'Power(KW)', 'Efficiency(%)', 'Efficiency_alarm']) + ccae_data[0])
                writer.writerow(pad_list_with_empty_strings(motor_cond_out_list) + ccae_data[1])
                # Write fault diagnosis result
                writer.writerow(
                    pad_list_with_empty_strings(['Icn_x(A)', 'Icn_y(A)', 'CN_thres(%)', 'CN_alarm', 'CN_range(A)']) +
                    ccae_data[2])
                writer.writerow(pad_list_with_empty_strings(motr_cn_sts_out_list) + ccae_data[3])
                writer.writerow(
                    pad_list_with_empty_strings(['Flux_mag(mWb)', 'Flux_thd(pu)', 'Flux_thres(%)', 'Demag_alarm']) +
                    ccae_data[4])
                writer.writerow(pad_list_with_empty_strings(Demag_status) + ccae_data[5])
                # Write RUL result
                rul_est = rul_result()
                writer.writerow(pad_list_with_empty_strings(
                    ['Health_Indicator', 'RUL_EN', 'RUL_alpha', 'RUL_beta', 'RUL_phi', 'RUL(min)', 'RUL_limit',
                     't_N(min)']) + ccae_data[6])
                writer.writerow(pad_list_with_empty_strings(list(rul_est.values())) + ccae_data[7])
                writer.writerow(pad_list_with_empty_strings(['FFT_res(Hz)']) + ccae_data[8])
                writer.writerow(
                    pad_list_with_empty_strings([Motor_global_vars.sampling_rate / Motor_global_vars.data_length]) +
                    ccae_data[9])
                # Write flux  signals
                writer.writerow(pad_list_with_empty_strings(
                    ['Flux_FFT_idx', 'FFT_result', 'Flux_x', 'Flux_y', 'Rul_t(HR) ', 'RUL_curve']) + ccae_data[10])
                for row_index in range(fast_out_data.shape[0]):
                    flux_datarow = pad_list_with_empty_strings(list(fast_out_data[row_index, :]), 8)
                    if row_index < 21 - 10:
                        flux_datarow = flux_datarow + ccae_data[row_index + 10 + 1]
                    pad_list_with_empty_strings(flux_datarow, 17)
                    # for row in flux_datarow:
                    #     formatted_row = [
                    #         f"{value:.{precision}f}" if isinstance(value, float) else value
                    #         for value in row
                    #     ]
                    writer.writerow(flux_datarow)
        except Exception as e:
            print(f'data saving error: {e}')
            print(f'{file_path} open fail, try again {delay}s later ')
            time.sleep(delay)  # sleep for 5 second

# rul result operation (still developing)
def rul_result():
    # use dictionary to storage RUL result
    rul_est = {'Health_Indicator': 0, 'RUL_EN': 0, 'RUL_alpha': 0,
               'RUL_beta': 0, 'RUL_phi': 0, 'RUL(min)': 0, 'RUL_limit': 0, 't_N(min)': 0}
    return rul_est


# simple fft calculation
def fft_test(signal_real, signal_imag, sampling_rate):
    T = 1 / sampling_rate
    N = len(signal_real)
    freqs = np.fft.fftfreq(N, T)
    freqs = np.fft.fftshift(freqs)
    real_part = np.array(signal_real)
    imaginary_part = np.array(signal_imag)
    complex_array = real_part + 1j * imaginary_part
    fft_result = np.fft.fft(complex_array)
    fft_result = np.fft.fftshift(fft_result / len(fft_result))
    return freqs, np.abs(fft_result)


# get motor operating condition
def get_motor_cond_list(motor_cond_raw):
    # conditions: 'Speed(Rpm)', 'Torque(N)', 'Power(KW)', 'Efficiency(%)', 'Efficiency_alarm'
    motr_cond_list = []
    motr_cond_list.append(u16_to_true_data(motor_cond_raw['speed'], pu_gain=Motor_global_vars.Base_Speed))
    motr_cond_list.append(u16_to_true_data(motor_cond_raw['torque'], pu_gain=Motor_global_vars.Base_Torque))
    motr_cond_list.append(u16_to_true_data(motor_cond_raw['power'], pu_gain=Motor_global_vars.Base_Power))
    # power is offset by 0.00001 to avoid divide by zero
    motr_cond_list.append(
        motr_cond_list[0] / 60 * 2 * math.pi * motr_cond_list[1] / (motr_cond_list[2] + 0.000001) * 100)
    motr_cond_list.append(int(motr_cond_list[3] < 90))
    return motr_cond_list


# get cn diagnosis result
def get_cn_sts_list(i_alpha, i_beta):

    # normalize the current data
    i_alpha = i_alpha/Motor_global_vars.Base_current
    i_beta = i_beta/Motor_global_vars.Base_current

    # calculate winding fault result by raw current
    L = len(i_alpha)  # data length
    #  calculate fft
    freqs, fft_result = fft_test(i_alpha, i_beta, Motor_global_vars.sampling_rate)
    # find frequency index of characteristic frequencies
    fund_freq_idx = np.argmax(fft_result)
    minus1_freq_idx = L - fund_freq_idx
    minus1_freq = freqs[minus1_freq_idx]
    fund_freq = freqs[fund_freq_idx]
    # find amplitude of characteristic frequencies
    fund_freq_amp = np.max(fft_result)
    minus1_freq_amp = fft_result[L - fund_freq_idx]
    # calculate CN value
    CN_value = minus1_freq_amp / fund_freq_amp
    # magnitude to rms
    motor_cn_sts = {
        'Icn_x': CN_value*32768+32767,
        'Icn_y': 0,
        'I_rms': fund_freq_amp*32768+32767,
    }

    # # fill data to winding fault report
    # motr_cn_list = []
    # cn_range = Motor_global_vars.cn_range_scale
    # motr_cn_list.append(CN_value)
    # motr_cn_list.append(0)
    # cn_thres = CN_value / cn_range * 100
    # motr_cn_list.append(CN_value / cn_range)
    # motr_cn_list.append(int(motr_cn_list[2] > 100))
    # motr_cn_list.append(cn_range)

    return motor_cn_sts, fund_freq, minus1_freq

# get the torque estimation
def estimate_torque(v_a_raw, v_c_raw, i_alpha, i_beta, speed_v=1800, debug=False):
    """
    Estimate the motor torque based on voltage and current inputs.
    :param v_a_raw: Voltage alpha component
    :param v_b_raw: Voltage beta component
    :param i_alpha: Current alpha component
    :param i_beta: Current beta component
    :param speed_v: Motor speed in rpm (default: 900)
    :param debug: Boolean flag to enable debugging plots (default: False)
    :return: Estimated torque array
    """

    v_a_raw = np.array(v_a_raw)
    v_c_raw = np.array(v_c_raw)
    i_alpha = np.array(i_alpha)
    i_beta  = np.array(i_beta)

    # offset calibration
    v_a_raw = v_a_raw - np.mean(v_a_raw)
    v_c_raw = v_c_raw - np.mean(v_c_raw)
    i_alpha = i_alpha - np.mean(i_alpha)
    i_beta = i_beta - np.mean(i_beta)

    # Preprocess the voltage data, transform the data to alpha-beta frame
    v_alpha = v_a_raw
    v_beta = v_c_raw #(-v_c_raw + v_a_raw - v_c_raw) / np.sqrt(3)

    class EMF:
        def __init__(self):
            self.Alpha = 0.0
            self.Beta = 0.0
            self.Alpha_last = 0.0
            self.Beta_last = 0.0
            self.Alpha_LPF = 0.0
            self.Beta_LPF = 0.0
            self.Alpha_LPF_last = 0.0
            self.Beta_LPF_last = 0.0

    def emf_to_lpf(sampling_time, lpf_radius, emf_obj):
        lpf_radius_t = lpf_radius * sampling_time
        emf_coef1 = sampling_time / (lpf_radius_t + 2)
        emf_coef2 = (lpf_radius_t - 2) / (lpf_radius_t + 2)

        emf_obj.Alpha_LPF = emf_coef1 * (emf_obj.Alpha_last + emf_obj.Alpha) - emf_coef2 * emf_obj.Alpha_LPF_last
        emf_obj.Beta_LPF = emf_coef1 * (emf_obj.Beta_last + emf_obj.Beta) - emf_coef2 * emf_obj.Beta_LPF_last

        emf_obj.Alpha_last = emf_obj.Alpha
        emf_obj.Beta_last = emf_obj.Beta

        emf_obj.Alpha_LPF_last = emf_obj.Alpha_LPF
        emf_obj.Beta_LPF_last = emf_obj.Beta_LPF

    def flux_comp(omega_e, lpf_radius):
        if np.abs(omega_e) < 1:
            mag_comp = 1.0
        else:
            mag_comp = np.abs(omega_e) / np.sqrt(omega_e ** 2 + lpf_radius ** 2)

        phase_comp = -57.29578 * np.arctan2(lpf_radius, omega_e) / 360  # Degree to radians conversion

        return mag_comp, phase_comp

    # Compute necessary parameters
    fs = Motor_global_vars.sampling_rate  # Sampling rate
    flux_rs = 0.1  # Motor stator resistance
    tsim = 1 / fs  # Time step

    we = (speed_v / 60) * (np.pi * 2)*2 # electrical angular velocity
    coef = 0.2
    cross_freq = 15.0

    intgr_bw_f = max((we / (np.pi * 2)) * coef, cross_freq)
    fast_wc = intgr_bw_f * (np.pi * 2)

    # Process each time step
    emf1 = EMF()
    alpha_lpf_values, beta_lpf_values = [], []
    alpha_raw_values, beta_raw_values = [], []

    for va, vb, ia, ib in zip(v_alpha, v_beta, i_alpha, i_beta):
        emf1.Alpha = va - (ia * flux_rs)
        emf1.Beta = vb - (ib * flux_rs)
        alpha_raw_values.append(emf1.Alpha)
        beta_raw_values.append(emf1.Beta)
        emf_to_lpf(tsim, fast_wc, emf1)
        alpha_lpf_values.append(emf1.Alpha_LPF)
        beta_lpf_values.append(emf1.Beta_LPF)

    # Flux compensation
    mag_comp2, phase_comp2 = flux_comp(we, fast_wc)

    # Apply phase and magnitude compensation
    alpha_compensated_values, beta_compensated_values = [], []
    for alpha, beta in zip(alpha_lpf_values, beta_lpf_values):
        ds = alpha * mag_comp2
        qs = beta * mag_comp2
        angle = phase_comp2
        sine, cosine = np.sin(angle), np.cos(angle)
        alpha_transformed = ds * cosine - qs * sine
        beta_transformed = qs * cosine + ds * sine
        alpha_compensated_values.append(alpha_transformed)
        beta_compensated_values.append(beta_transformed)

    # Torque estimation
    torque_v = 1.5 * Motor_global_vars.Motor_P/2 * ((np.array(alpha_compensated_values) * i_beta) - (np.array(beta_compensated_values) * i_alpha))
    # Power and efficiency estimation
    Power_M= np.mean(torque_v[-Motor_global_vars.data_length:]*we)
    Power_E = np.mean(3 / 2 * (v_alpha * i_alpha + v_beta * i_beta))
    efficiency = Power_M / Power_E * 100
    power_sts = {
        'Power_M': Power_M,
        'Power_E': Power_E,
        'Efficiency': efficiency,
        'Efficiency_alarm': int(efficiency < 90)
    }

    if debug :

        print("Estimated Torque:", np.mean(torque_v[-Motor_global_vars.data_length:]))
        # print result
        for key, value in power_sts.items():
            print(f"{key}: {value}")

        time = np.arange(len(v_alpha)) * tsim

        # plot the flux values
        plt.figure(figsize=(10, 5))
        plt.plot(time, alpha_compensated_values, label='Flux Alpha')
        plt.plot(time, beta_compensated_values, label='Flux Beta ')
        plt.xlabel('Time (s)')
        plt.ylabel('Flux Values')
        plt.legend()
        plt.title('Flux Values')
        plt.grid()
        plt.show(block=False)

        # plot the voltage values
        plt.figure(figsize=(10, 5))
        plt.plot(time, v_alpha, label='Voltage Beta (raw)')
        plt.plot(time, v_beta, label='Voltage Beta (raw)')
        plt.xlabel('Time (s)')
        plt.ylabel('Voltage Values')
        plt.legend()
        plt.title('Voltage Values')
        plt.grid()
        plt.show(block=False)

        # plot the current values
        plt.figure(figsize=(10, 5))
        plt.plot(time, i_alpha, label='Current Alpha (raw)')
        plt.plot(time, i_beta, label='Current Beta (raw)')
        plt.xlabel('Time (s)')
        plt.ylabel('Current Values')
        plt.legend()
        plt.title('Current Values')
        plt.grid()
        plt.show(block=False)

        # plot the EMF values
        plt.figure(figsize=(10, 5))
        plt.plot(time, alpha_raw_values, label='EMF Alpha (raw)')
        plt.plot(time, beta_raw_values, label='EMF Beta (raw)')
        plt.xlabel('Time (s)')
        plt.ylabel('EMF Values')
        plt.legend()
        plt.title('EMF Values')
        plt.grid()
        plt.show(block=False)

        # # plot vectors for torque estimation
        # plt.figure(figsize=(10, 5))
        # idx = -1  # time index
        # x1, y1 = 0, 0  # origin
        # x2, y2 = i_alpha[idx], i_beta[idx]  # current vector
        # x3, y3 = (alpha_compensated_values[idx],  # flux vector
        #           beta_compensated_values[idx])
        # # 繪製線段
        # plt.plot([x1, x2], [y1, y2], marker='o', linestyle='-', color='b')
        # plt.plot([x1, x3], [y1, y3], marker='x', linestyle='-', color='r')
        # # 設定圖形標籤
        # plt.xlabel('X-axis')
        # plt.ylabel('Y-axis')
        # plt.title('Motor vector plot ')
        # plt.show(block=False)

        # plot torque estimation
        plt.figure(figsize=(10, 5))
        plt.plot(time, torque_v, label='Torque (Voltage Model)')
        plt.xlabel('Time (s)')
        plt.ylabel('Torque (N.m)')
        plt.legend()
        plt.title('Torque Estimation')
        plt.grid()
        plt.show(block=False)

        fig, ax1 = plt.subplots(figsize=(10, 5))
        ax1.set_xlabel('Time (s)')
        ax1.set_ylabel('EMF Alpha (Raw)', color='tab:blue')
        ax1.plot(time, alpha_raw_values, label='EMF Alpha (Raw)', color='tab:blue')
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.legend(loc='upper left')

        ax2 = ax1.twinx()
        ax2.set_ylabel('EMF Alpha (Filtered)', color='tab:red')
        # ax2.plot(time, alpha_lpf_values, label='EMF Alpha (Filtered)', color='tab:red')
        ax2.plot(time, alpha_compensated_values, label='EMF Alpha (Compensated)', color='tab:red')
        ax2.tick_params(axis='y', labelcolor='tab:red')
        ax2.legend(loc='upper right')

        plt.title('EMF Alpha - Raw vs Filtered')
        plt.grid()
        plt.show()
    # return the torque value and the estimated flux
    return torque_v, alpha_compensated_values, beta_compensated_values, v_alpha, v_beta, power_sts

# rescale the Uint16 data to float
def u16_to_true_data(u16_data, pu_gain=1):
    float_data = (u16_data - 32768) / 32768 * pu_gain
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
    pm_strength = np.average(np.sqrt(flux_alpha ** 2 + flux_beta ** 2))
    pm_thres = min(pm_strength / Motor_global_vars.Base_flux, 1) * 100
    flux_thd = calculate_thd_with_fftshift(flux_fft)
    pm_alarm = int(pm_thres < 90)
    demag_status = [pm_strength, pm_thres, flux_thd, pm_alarm]
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
    thd = np.sqrt(harmonic_power) / V1  # 轉換為百分比

    return thd

if __name__ == "__main__":

    # read the data while skip the first 2 row to avoid parse error
    # df = pd.read_csv('IPC_test_data/Motor_test_data.csv', skiprows=1)
    df = pd.read_csv('IPC_test_data/RUL_Data_5_962.csv', skiprows=1)

    v_a = df['V_alpha'].to_numpy()
    v_c = df['V_beta'].to_numpy()
    i_alpha = df['I_alpha'].to_numpy()
    i_beta = df['I_beta'].to_numpy()

    motor_cn_sts, fund_freq, minus1_freq = get_cn_sts_list(i_alpha, i_beta)
    print(f"fundamental frequency: {fund_freq} Hz")
    # print result
    for key, value in motor_cn_sts.items():
        print(f"{key}: {value}")
    torque, alpha_compensated_values, beta_compensated_values, v_alpha, v_beta, power_sts = estimate_torque(v_a, v_c, i_alpha, i_beta, debug=True)





