#
# Copyright (C) 2018 Pico Technology Ltd. See LICENSE file for terms.
#
# PS4000 BLOCK MODE EXAMPLE
# This example opens a 4000 driver device, sets up two channels and a trigger then collects a block of data.
# This data is then plotted as mV against time in ns.

import ctypes
import numpy as np
from picosdk.ps4000 import ps4000 as ps
import picosdk.ps4000 as p4000
import matplotlib.pyplot as plt
from picosdk.functions import adc2mV, assert_pico_ok

acc_gain=200 # gain of accelerometer
pico_range_dict={
"PS4000_ACCELEROMETER_20MV":40,
    "PS4000_ACCELEROMETER_50MV":100,
    "PS4000_ACCELEROMETER_100MV":200,
    "PS4000_ACCELEROMETER_200MV":400,
    "PS4000_ACCELEROMETER_500MV":1000,
    "PS4000_ACCELEROMETER_1V":2000,
    "PS4000_ACCELEROMETER_2V":4000,
    "PS4000_ACCELEROMETER_5V":10000,
    "PS4000_ACCELEROMETER_10V":20000,
    "PS4000_ACCELEROMETER_20V":40000,
    "PS4000_ACCELEROMETER_50V":100000,
    "PS4000_ACCELEROMETER_100V":200000,
}

def pico_setup_acc(data_length):

    # Create chandle and status ready for use
    chandle = ctypes.c_int16()
    status = {}

    # Open 5000 series PicoScope
    # Returns handle to chandle for use in future API functions
    status["openunit"] = ps.ps4000OpenUnit(ctypes.byref(chandle))
    assert_pico_ok(status["openunit"])

    # Set up channel A
    # handle = chandle
    # channel = PS4000_CHANNEL_A = 0
    # enabled = 1
    # coupling type = PS4000_DC = 1
    chARange = ps.PS4000_RANGE["PS4000_ACCELEROMETER_50MV"]
    status["setChA"] = ps.ps4000SetChannel(chandle, 0, 1, 1, chARange)
    assert_pico_ok(status["setChA"])

    # Set up channel B (disable)
    # handle = chandle
    # channel = PS4000_CHANNEL_B = 1
    # enabled = 1
    # coupling type = PS4000_DC = 1
    # range = PS4000_2V = 7
    chBRange = 7
    status["setChB"] = ps.ps4000SetChannel(chandle, 1, 0, 1, chBRange)
    assert_pico_ok(status["setChB"])

    #  trigger
    status["trigger"] = ps.ps4000SetSimpleTrigger(chandle, 1, 0, 1024, 2, 0, 1000)
    assert_pico_ok(status["trigger"])

    # # standard trigger
    # status["ChannelProperties"] = ps.ps4000SetTriggerChannelProperties(chandle, None , 0, 0, 0)
    # assert_pico_ok(status["ChannelProperties"])
    #
    # status["ChannelConditions"] = ps.ps4000SetTriggerChannelConditions(chandle, None ,0)
    # assert_pico_ok(status["ChannelConditions"])
    #
    # status["ChannelDirections"] = ps.ps4000SetTriggerChannelDirections(chandle, 0, 0, 0, 0, 0, 0)
    # assert_pico_ok(status["ChannelDirections"])
    #
    # status["TriggerDelay"] = ps.ps4000SetTriggerDelay(chandle, 0)
    # assert_pico_ok(status["TriggerDelay"])
    #
    # status["PulseWidthQualifier"] = ps.ps4000SetPulseWidthQualifier(chandle, 0, 0, 0, 0, 0, 0)
    # assert_pico_ok(status["PulseWidthQualifier"])


    # Set number of pre and post trigger samples to be collected
    preTriggerSamples = 0
    postTriggerSamples = data_length
    maxSamples = preTriggerSamples + postTriggerSamples

    # Get timebase information
    # Warning: When using this example it may not be possible to access all Timebases as all channels are enabled by default when opening the scope.
    # To access these Timebases, set any unused analogue channels to off.
    # handle = chandle
    # timebase = 51 -> (51-1)/20,000,000 ns =40k sampling rate
    # oversample =2: resample for denoise -> 20k sampling rate
    # noSamples = maxSamples
    # pointer to timeIntervalNanoseconds = ctypes.byref(timeIntervalns)
    # pointer to maxSamples = ctypes.byref(returnedMaxSamples)
    # segment index = 0
    timebase = 51
    timeIntervalns = ctypes.c_float()
    returnedMaxSamples = ctypes.c_int32()
    oversample = ctypes.c_int16(1)
    status["getTimebase2"] = ps.ps4000GetTimebase2(chandle, timebase, maxSamples, ctypes.byref(timeIntervalns), oversample, ctypes.byref(returnedMaxSamples), 0)
    assert_pico_ok(status["getTimebase2"])

    runblock_settings={'preTriggerSamples':preTriggerSamples,
                      'postTriggerSamples':postTriggerSamples,
                      'timebase':timebase,
                      'oversample':oversample}

    return status, chandle, runblock_settings, chARange

def runblock_pico_A(status, chandle, runblock_settings):
    preTriggerSamples=runblock_settings['preTriggerSamples']
    postTriggerSamples=runblock_settings['postTriggerSamples']
    timebase=runblock_settings['timebase']
    oversample=runblock_settings['oversample']

    # Run block capture
    # handle = chandle
    # number of pre-trigger samples = preTriggerSamples
    # number of post-trigger samples = PostTriggerSamples
    # timebase = 8 = 80 ns = timebase (see Programmer's guide for mre information on timebases)
    # time indisposed ms = None (not needed in the example)
    # segment index = 0
    # lpReady = None (using ps4000IsReady rather than ps4000BlockReady)
    # pParameter = None
    status["runBlock"] = ps.ps4000RunBlock(chandle, preTriggerSamples, postTriggerSamples, timebase, oversample, None,
                                           0, None, None)
    assert_pico_ok(status["runBlock"])

def get_pico_values(status, chandle, runblock_settings, chARange):

    maxSamples=runblock_settings['preTriggerSamples']+runblock_settings['postTriggerSamples']

    # Check for data collection to finish using ps4000IsReady
    ready = ctypes.c_int16(0)
    check = ctypes.c_int16(0)
    while ready.value == check.value:
        status["isReady"] = ps.ps4000IsReady(chandle, ctypes.byref(ready))

    # Create buffers ready for assigning pointers for data collection
    bufferAMax = (ctypes.c_int16 * maxSamples)()
    bufferAMin = (ctypes.c_int16 * maxSamples)()  # used for downsampling which isn't in the scope of this example

    # Set data buffer location for data collection from channel A
    # handle = chandle
    # source = PS4000_CHANNEL_A = 0
    # pointer to buffer max = ctypes.byref(bufferAMax)
    # pointer to buffer min = ctypes.byref(bufferAMin)
    # buffer length = maxSamples
    status["setDataBuffersA"] = ps.ps4000SetDataBuffers(chandle, 0, ctypes.byref(bufferAMax),
                                                        ctypes.byref(bufferAMin), maxSamples)
    assert_pico_ok(status["setDataBuffersA"])

    # create overflow loaction
    overflow = ctypes.c_int16()
    # create converted type maxSamples
    cmaxSamples = ctypes.c_int32(maxSamples)

    # Retried data from scope to buffers assigned above
    # handle = chandle
    # start index = 0
    # pointer to number of samples = ctypes.byref(cmaxSamples)
    # downsample ratio = 0
    # downsample ratio mode = PS4000_RATIO_MODE_NONE
    # pointer to overflow = ctypes.byref(overflow))
    status["getValues"] = ps.ps4000GetValues(chandle, 0, ctypes.byref(cmaxSamples), 0, 0, 0, ctypes.byref(overflow))
    assert_pico_ok(status["getValues"])
    global acc_gain
    if overflow:
        chARange =chARange+1
        pico_range = next((k for k, v in ps.PS4000_RANGE.items() if v == chARange), None)
        status["setChA"] = ps.ps4000SetChannel(chandle, 0, 1, 1, chARange)
        assert_pico_ok(status["setChA"])
        print(f'Pico overflow, change ADC range to {pico_range}')
        print(f'chARange: {chARange}')
        acc_gain = pico_range_dict[pico_range]

    # convert ADC result to acceleration in g
    # byte data  to g, 1000(if +-500mV)/65535*1g/1021mV
    adc2gChAMax = [x * acc_gain / 65535 / 1021 for x in bufferAMax]

    return chARange, adc2gChAMax

def pico_close(status,chandle):
    # Close unit Disconnect the scope
    # handle = chandle
    status["close"] = ps.ps4000CloseUnit(chandle)
    assert_pico_ok(status["close"])

