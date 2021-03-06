import time, math
import numpy as np


def resample(ts, values, num_samples=None):
    """Convert a list of times and a list of values to evenly spaced samples with linear interpolation"""
    assert np.all(np.diff(ts) >= 0)
    if num_samples == None:
        num_samples = math.ceil((ts[-1] - ts[0]) / guess_period(ts))
    ts = normalize(ts)
    return np.interp(np.linspace(0.0, 1.0, num_samples), ts, values)

def guess_period(ts):
    return np.median([ts[i+1] - ts[i] for i in range(len(ts) - 1)])

def upsample(signal, factor):
    """Increase the sampling rate of a signal (by an integer factor), with linear interpolation"""
    assert type(factor) == int and factor > 1
    result = [None] * ((len(signal) - 1) * factor)
    for i, v in enumerate(signal):
        if i == len(signal) - 1:
            result[-1] = v
            break
        v_ = signal[i+1]
        delta = v_ - v
        for j in range(factor):
            f = (i * factor) + j
            result[f] = v + ((delta / factor) * j)
    return result     

def downsample(signal, factor):
    """Decrease the sampling rate of a signal (by an integer factor), with averaging"""    
    signal = np.array(signal)
    xs = signal.shape[0]
    signal = signal[:xs - (xs % int(factor))]
    result = np.mean(np.concatenate([[signal[i::factor] for i in range(factor)]]), axis=0)
    return result     

def normalize(signal, minimum=None, maximum=None):
    """Normalize a signal to the range 0, 1. Uses the minimum and maximum observed in the data unless explicitly passed."""
    signal = np.array(signal).astype('float')
    if minimum is None:
        minimum = np.min(signal)
    if maximum is None:
        maximum = np.max(signal)
    signal -= minimum
    maximum -= minimum
    signal /= maximum
    signal = np.clip(signal, 0.0, 1.0)
    return signal    

def rescale(signal, low, high):
    """Rescale a signal (normalize it first) to a given range"""
    signal = np.array(signal)
    signal *= high - low
    signal += low
    return signal

def make_audio(signal):
    signal = normalize(signal)
    signal = rescale(signal, -32768, 32767)
    signal = signal.astype(np.int16)
    return signal

def magnitude(signal):
    """Absolute value of a signal"""
    ## why am I seeing some negative values?
    signal = np.array(signal)
    signal = np.absolute(signal)
    signal = threshold(signal, 0)
    return signal

def threshold(signal, value):
    """Drop all values in a signal to 0 if below the given threshold"""
    signal = np.array(signal)
    return (signal > value) * signal

def limit(signal, value):
    """Limit all values in a signal to the given value"""
    return np.clip(signal, 0, value)

def remove_shots(signal, threshold_high=None, threshold_low=None, devs=None, positive_only=False, nones=False, zeros=False, jump=None):
    """Replace values in a signal that violate a threshold, vary by a given number of deviations, or exceed a jump by interpolation between neigboring 'good' samples"""
    """Can be used to fill in missing values in a signal: mark them as None and run this function without other parameters"""        
    signal = signal.copy()
    shot_indexes = []
    if threshold_high is not None:
        shot_indexes += [i for (i, sample) in enumerate(signal) if sample > threshold_high]
    if threshold_low is not None:
        shot_indexes += [i for (i, sample) in enumerate(signal) if sample < threshold_low]
    if devs is not None:
        average = np.average(signal)
        deviation = np.std(signal)
        shot_indexes += [i for (i, sample) in enumerate(signal) if (sample - average if positive_only else abs(sample - average)) > deviation * devs]
    if nones:
        shot_indexes += [i for (i, sample) in enumerate(signal) if sample is None]
    if zeros:
        shot_indexes += [i for (i, sample) in enumerate(signal) if sample == 0]
    if jump is not None:
        # note that noise at the beginning of the signal can really screw up jump
        i = 0
        while i < (len(signal) - 1):
            j = i + 1
            while j < len(signal) and abs(signal[j] - signal[i]) > jump:
                shot_indexes.append(j)
                j += 1
            i = j    
    shot_indexes = list(set(shot_indexes))
    shot_indexes.sort()
    i = 0
    while i < len(shot_indexes):    
        shot_index = shot_indexes[i]   
        start_index = shot_index - 1
        stop_index = shot_index + 1        
        j = 1
        while (i+j) < len(shot_indexes) and stop_index == shot_indexes[i+j]:    
            stop_index += 1
            j += 1            
        if stop_index == len(signal):
            stop_index = len(signal) - 1
        pos = (shot_index - start_index) / (stop_index - start_index)
        start_value = signal[start_index] if start_index > 0 else np.average([v for v in signal if v is not None])
        if signal[stop_index] is not None:
            signal[shot_index] = start_value + ((signal[stop_index] - start_value) * pos)
        else:
            signal[shot_index] = start_value
        i += 1
    return signal

def compress(signal, value=2.0, normalize=False):
    """Compress the signal by an exponential value (will expand if value<0)"""
    signal = np.array(signal)
    signal = np.power(signal, 1.0 / value)
    return normalize(signal) if normalize else signal

def smooth(signal, size=10, window='blackman'):
    """Apply weighted moving average (aka low-pass filter) via convolution function to a signal with the given window shape and size"""
    """This is going to be faster than highpass_filter"""
    types = ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']
    signal = np.array(signal)
    if size < 3:
        return signal
    s = np.r_[2 * signal[0] - signal[size:1:-1], signal, 2 * signal[-1] - signal[-1:-size:-1]]
    if window == 'flat': # running average
        w = np.ones(size,'d')
    else:
        w = getattr(np, window)(size) # get a series of weights that matches the window and is the correct size 
    y = np.convolve(w / w.sum(), s, mode='same') # convolve the signals
    return y[size - 1:-size + 1]

def detect_onsets(signal):
    onsets = []
    for i in range(len(signal) - 1):
        if signal[i] == 0 and signal[i+1] > 0:
            onsets.append(i)
    return onsets

def detect_peaks(signal, lookahead=300, delta=0):   ## probably a better scipy module...
    """ Detect the local maximas and minimas in a signal
        lookahead -- samples to look ahead from a potential peak to see if a bigger one is coming
        delta -- minimum difference between a peak and surrounding points to be considered a peak (no hills) and makes things faster
        Note: careful if you have flat regions, may affect lookahead
    """    
    signal = np.array(signal)
    peaks = []
    valleys = []
    min_value, max_value = np.Inf, -np.Inf    
    for index, value in enumerate(signal[:-lookahead]):        
        if value > max_value:
            max_value = value
            max_pos = index
        if value < min_value:
            min_value = value
            min_pos = index    
        if value < max_value - delta and max_value != np.Inf:
            if signal[index:index + lookahead].max() < max_value:
                peaks.append([max_pos, max_value])
                drop_first_peak = True
                max_value = np.Inf
                min_value = np.Inf
                if index + lookahead >= signal.size:
                    break
                continue
        if value > min_value + delta and min_value != -np.Inf:
            if signal[index:index + lookahead].min() > min_value:
                valleys.append([min_pos, min_value])
                drop_first_valley = True
                min_value = -np.Inf
                max_value = -np.Inf
                if index + lookahead >= signal.size:
                    break
    return peaks, valleys

def autocorrelate(signal):
    """Get the auto-correlation function of a signal"""    
    x = np.hstack((signal, np.zeros(len(signal))))
    sp = np.fft.rfft(x) 
    tmp = np.empty_like(sp)
    tmp = np.conj(sp, tmp)
    tmp = np.multiply(tmp, sp, tmp)
    ac = np.fft.irfft(tmp)
    ac = np.divide(ac, signal.size, ac)[:math.floor(signal.size / 2)] 
    tmp = signal.size / (signal.size - np.arange(math.floor(signal.size / 2), dtype=np.float64)) 
    ac = np.multiply(ac, tmp, ac)
    ac = np.concatenate([ac, np.full(signal.size - ac.size, np.mean(ac))])  # note: technically the last half of the array should be zeros, but this works better for visualization and peak detection
    return normalize(ac)

def derivative(signal):
    """Return a signal that is the derivative function of a given signal"""
    def f(x):
        x = int(x)
        return signal[x]
    def df(x, h=0.1e-5):
        return (f(x + h * 0.5) - f(x - h * 0.5)) / h
    return np.array([df(x) for x in range(len(signal))])

def integral(signal):
    """Return a signal that is the integral function of a given signal"""
    result = []
    v = 0.0    
    for i in range(len(signal)):
        v += signal[i]
        result.append(v)
    return np.array(result)

def delta(signal):
    """Return a signal that is the change between each sample"""
    signal = np.array(signal)
    diff = np.diff(signal)
    if len(signal.shape) > 1:
        dims = signal.shape[1]
        signal = np.concatenate((np.zeros((1, dims)), diff))
    else:
        signal = np.concatenate((np.zeros(1), diff))
    return signal

def flip(signal, num_samples=None):
    """Flip the axes of a 1D signal"""
    ts = signal
    values = list(range(0, len(signal)))    
    signal = resample(ts, values, num_samples)
    return signal

def f(signal, x):
    """Return y value given a signal and a given x"""
    if x <= 1:
        indexf = x * (len(signal) - 1)
    else:
        indexf = x
    pos = indexf % 1.0
    value = (signal[math.floor(indexf)] * (1.0 - pos)) + (signal[math.ceil(indexf)] * pos)
    return value

def trendline(signal):
    """Returns a line (slope, intersect) that is the linear regression given a series of values."""
    signal = list(signal)
    n = len(signal) - 1
    sum_x = 0
    sum_y = 0
    sum_xx = 0
    sum_xy = 0
    for i in range(1, n + 1):
        x = i
        y = signal[i]
        sum_x = sum_x + x
        sum_y = sum_y + y
        xx = math.pow(x, 2)
        sum_xx = sum_xx + xx
        xy = x*y
        sum_xy = sum_xy + xy
    try:    
        a = (-sum_x * sum_xy + sum_xx * sum_y) / (n * sum_xx - sum_x * sum_x)
        b = (-sum_x * sum_y + n * sum_xy) / (n * sum_xx - sum_x * sum_x)
    except ZeroDivisionError:
        a, b = 0, 0    
    return (b, a) # (slope, intersect)

    
def bandpass_filter(signal, sampling_rate, lowcut, highcut, order=6):
    """In hz"""
    from scipy.signal import butter, lfilter
    nyquist = 0.5 * sampling_rate
    low = lowcut / nyquist
    high = highcut / nyquist
    b, a = butter(order, [low, high], btype='band')
    signal = lfilter(b, a, signal)
    return signal
    
def lowpass_filter(signal, sampling_rate, cutoff, order=6):   
    """fyi, convolution-based smooth is probably faster"""
    from scipy.signal import butter, lfilter 
    nyquist = 0.5 * sampling_rate
    normal_cutoff = cutoff / nyquist
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    signal = lfilter(b, a, signal)
    return signal

def highpass_filter(signal, sampling_rate, cutoff, order=6):    
    from scipy.signal import butter, lfilter
    nyquist = 0.5 * sampling_rate
    normal_cutoff = cutoff / nyquist
    b, a = butter(order, normal_cutoff, btype='high', analog=False)
    signal = lfilter(b, a, signal)
    return signal    