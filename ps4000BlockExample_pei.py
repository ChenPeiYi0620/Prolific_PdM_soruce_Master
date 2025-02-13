import ctypes
import numpy as np
from picosdk.ps4000 import ps4000 as ps
import matplotlib.pyplot as plt
from picosdk.functions import adc2mV, assert_pico_ok


def setup_pico():
    chandle = ctypes.c_int16()
    status = {}

    # Open 5000 series PicoScope
    status["openunit"] = ps.ps4000OpenUnit(ctypes.byref(chandle))
    assert_pico_ok(status["openunit"])

    return chandle, status


def configure_channel(chandle, pico_scale, status):
    # Set up channel A
    chARange = ps.PS4000_RANGE[pico_scale]
    status["setChA"] = ps.ps4000SetChannel(chandle, 0, 1, 1, chARange)
    assert_pico_ok(status["setChA"])

    # Set up channel B (disable)
    chBRange = 7
    status["setChB"] = ps.ps4000SetChannel(chandle, 1, 0, 1, chBRange)
    assert_pico_ok(status["setChB"])

    # Trigger
    status["trigger"] = ps.ps4000SetSimpleTrigger(chandle, 1, 0, 1024, 2, 0, 1000)
    assert_pico_ok(status["trigger"])


def collect_data(chandle, status, pico_range_dict):
    preTriggerSamples = 0
    postTriggerSamples = 5000
    maxSamples = preTriggerSamples + postTriggerSamples
    timebase = 51
    timeIntervalns = ctypes.c_float()
    returnedMaxSamples = ctypes.c_int32()
    oversample = ctypes.c_int16(1)

    status["getTimebase2"] = ps.ps4000GetTimebase2(chandle, timebase, maxSamples, ctypes.byref(timeIntervalns),
                                                   oversample, ctypes.byref(returnedMaxSamples), 0)
    assert_pico_ok(status["getTimebase2"])

    status["runBlock"] = ps.ps4000RunBlock(chandle, preTriggerSamples, postTriggerSamples, timebase, oversample, None,
                                           0, None, None)
    assert_pico_ok(status["runBlock"])

    ready = ctypes.c_int16(0)
    while ready.value == 0:
        status["isReady"] = ps.ps4000IsReady(chandle, ctypes.byref(ready))

    bufferAMax = (ctypes.c_int16 * maxSamples)()
    bufferAMin = (ctypes.c_int16 * maxSamples)()
    status["setDataBuffersA"] = ps.ps4000SetDataBuffers(chandle, 0, ctypes.byref(bufferAMax), ctypes.byref(bufferAMin),
                                                        maxSamples)
    assert_pico_ok(status["setDataBuffersA"])

    overflow = ctypes.c_int16()
    cmaxSamples = ctypes.c_int32(maxSamples)
    status["getValues"] = ps.ps4000GetValues(chandle, 0, ctypes.byref(cmaxSamples), 0, 0, 0, ctypes.byref(overflow))
    assert_pico_ok(status["getValues"])

    if overflow:
        print("Pico overflow occurred!")

    bufferAMax_py = list(bufferAMax)
    adc2gChAMax = [x * pico_range_dict[pico_scale] / 65535 / 1021 for x in bufferAMax_py]
    time = np.linspace(0, (cmaxSamples.value - 1) * timeIntervalns.value, cmaxSamples.value)

    return time, adc2gChAMax


def close_pico(chandle, status):
    status["stop"] = ps.ps4000Stop(chandle)
    assert_pico_ok(status["stop"])
    status["close"] = ps.ps4000CloseUnit(chandle)
    assert_pico_ok(status["close"])
    print(status)


def plot_data(time_list, data_list, labels):
    fig, axes = plt.subplots(len(time_list), 1, figsize=(10, 5 * len(time_list)))
    if len(time_list) == 1:
        axes = [axes]
    for ax, time, data, label in zip(axes, time_list, data_list, labels):
        ax.plot(time, data, label=label)
        ax.set_xlabel("Time (ns)")
        ax.set_ylabel("Acceleration (g)")
        ax.legend()
    plt.show()


if __name__ == "__main__":
    pico_range_dict = {
        "PS4000_ACCELEROMETER_50MV": 100,
        "PS4000_ACCELEROMETER_100MV": 200,
        "PS4000_ACCELEROMETER_200MV": 400,
        "PS4000_ACCELEROMETER_500MV": 1000,
        "PS4000_ACCELEROMETER_1V": 2000,
        "PS4000_ACCELEROMETER_2V": 4000,
    }

    chandle, status = setup_pico()
    time_data_list = []
    adc_data_list = []
    labels = []

    for pico_scale in pico_range_dict.keys():
        configure_channel(chandle, pico_scale, status)
        time_data, adc_data = collect_data(chandle, status, pico_range_dict)
        time_data_list.append(time_data)
        adc_data_list.append(adc_data)
        labels.append(f"{pico_scale} (RMS: { np.sqrt(np.mean(np.square(adc_data))):.2f})")

    close_pico(chandle, status)
    plot_data(time_data_list, adc_data_list, labels)
