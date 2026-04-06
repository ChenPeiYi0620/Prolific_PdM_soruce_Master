# Define the global variables of motor and AQ box

import pandas as pd
import numpy as np
import os

# function to extract parameter from dataframe
def get_parameter_from_df(df,para_name,default_value):
    # file read fail, return default value
    if isinstance(df, list) :
        return default_value
    try:
        parameter_val = df[para_name]
        parameter_val = parameter_val[0]
    except:
        print(f'parameter read error, {para_name} is set by default value')
        return default_value
    if isinstance(parameter_val, (float, np.integer)):
        return float(parameter_val) if isinstance(parameter_val, float) else int(parameter_val)
    elif isinstance(parameter_val, str):
        return parameter_val
    else:
        return default_value

csv_candidates = [
    'AQbox_Parameters.csv',
    os.path.join(os.path.dirname(__file__), 'AQbox_Parameters.csv'),
    os.path.join(os.path.dirname(__file__), '..', 'AQbox_Parameters.csv'),
]

parameters = []
for csv_path in csv_candidates:
    try:
        parameters = pd.read_csv(csv_path)
        break
    except Exception:
        continue

if isinstance(parameters, list):
    print('AQbox_Parameters.csv read fail, use default parameters')

Motor_Rs=get_parameter_from_df(parameters,'Motor_Rs(Ohm)',12.5)
Motor_Ls=get_parameter_from_df(parameters,'Motor_LS(H)',0.00906)
Motor_P=get_parameter_from_df(parameters,'Motor_P',8)
Base_Speed=get_parameter_from_df(parameters,'Base_Speed(Rpm)',3000)
Base_Torque=get_parameter_from_df(parameters,'Base_Torque(N)',1)
Base_Power=get_parameter_from_df(parameters,'Base_Power(W)',1)
Base_current=get_parameter_from_df(parameters,'Base_Current(A)',98.274)
Base_voltage=get_parameter_from_df(parameters,'Base_Voltage(V)',300)
Base_flux=get_parameter_from_df(parameters,'Base_Flux(Wb)',0.05)
cn_range_scale=get_parameter_from_df(parameters,'cn_range_scale',0.05)
data_length=get_parameter_from_df(parameters,'data_length',500)
max_tries=get_parameter_from_df(parameters,'Max_tries',3)
update_period=get_parameter_from_df(parameters,'Update_period',300)
RUL_update_times=get_parameter_from_df(parameters,'RUL_update_times',2)
V_measure_mode=get_parameter_from_df(parameters,'V_measure_mode','Vadc_mode')
fast_update_period=get_parameter_from_df(parameters,'FAST_period',60) # 1 min
rul_update_period=get_parameter_from_df(parameters,'RUL_period',300) # 5 min
transmit_test_flag=get_parameter_from_df(parameters,'Transmit_test_flag',0)
collection_times=get_parameter_from_df(parameters,'collection_times',40)
outlier_number=get_parameter_from_df(parameters,'outlier_number',10)

Data_folder_path=parameters['Record File Path']
Data_folder_path=Data_folder_path[0]

# sampling rate *** 重要:此採樣率為IPC計算使用，實際採樣率設定在MCU裡面 ***
sampling_rate=10000

# vibration alarm threshold (g)
acc_threshold=0.5

# for motor ID
motor_id={
    1: "PUMP_A0101",
    2: "PUMP_A0102",
    3: "PUMP_A0103",
    4: "PUMP_A0104",
    5: "PUMP_A0105",
    6: "PUMP_A0106",
    7: "PUMP_A0107",
    8: "PUMP_A0108"
}
print('parameter set up complete')



# motor variables, Rs=0~20 Ohm,Ls=0~0.001 H, P=0~128
# # parameter declairation
# MAX_RETRIES=3 # Max retry times in each collection cycle
# AQ_PERIOD=60 #Basse data update period (1 min)
# RUL_update_times = 2  # Actual RUL update time = RUL_update_times*AQ_PERIOD

# Motor_Rs=0
# Motor_Ls=0.00906
# Motor_P=8
#
# # PU gains
# Base_Speed=3000     #rpm
# Base_Torque=1       #Nm
# Base_Power=1        #kW
# Base_current=15.389 #A
# Base_voltage=300    # Vdc
# Base_flux=0.05     #Wb
#
# # Diagnosis parameters
# cn_range_scale=0.05 #5# cn fault boundary
#
# # FFT parameters
# data_length=500
