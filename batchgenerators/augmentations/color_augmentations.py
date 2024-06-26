# Copyright 2021 Division of Medical Image Computing, German Cancer Research Center (DKFZ)
# and Applied Computer Vision Lab, Helmholtz Imaging Platform
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Tuple, Callable, Union

import numpy as np

from batchgenerators.augmentations.utils import general_cc_var_num_channels, illumination_jitter, get_broadcast_axes, \
    reverse_broadcast


def get_augment_contrast_factor(contrast_range: Union[Tuple[float, float], Callable[[], float]],
                                per_channel: bool,
                                size: int,
                                broadcast_size: int):
    if per_channel:
        factor = []
        for _ in range(size):
            if callable(contrast_range):
                factor.append(contrast_range())
            elif contrast_range[0] < 1 and np.random.random() < 0.5:
                factor.append(np.random.uniform(contrast_range[0], 1))
            else:
                factor.append(np.random.uniform(max(contrast_range[0], 1), contrast_range[1]))

        factor = reverse_broadcast(np.array(factor), get_broadcast_axes(broadcast_size))
    else:
        if callable(contrast_range):
            factor = contrast_range()
        elif contrast_range[0] < 1 and np.random.random() < 0.5:
            factor = np.random.uniform(contrast_range[0], 1)
        else:
            factor = np.random.uniform(max(contrast_range[0], 1), contrast_range[1])

    return factor


def augment_contrast(data_sample: np.ndarray,
                     contrast_range: Union[Tuple[float, float], Callable[[], float]] = (0.75, 1.25),
                     preserve_range: bool = True,
                     per_channel: bool = True,
                     p_per_channel: float = 1,
                     batched=False) -> np.ndarray:
    mask = np.random.uniform(size=data_sample.shape[:2] if batched else data_sample.shape[0]) < p_per_channel
    if np.any(mask):
        workon = data_sample[mask]
        factor = get_augment_contrast_factor(contrast_range, per_channel, len(workon), workon.ndim)
        axes = tuple(range(1, workon.ndim))
        mean = workon.mean(axis=axes, keepdims=True)
        if preserve_range:
            minm = workon.min(axis=axes, keepdims=True)
            maxm = workon.max(axis=axes, keepdims=True)

        data_sample[mask] = workon * factor + mean * (1 - factor)  # writing directly in data_sample

        if preserve_range:
            np.clip(data_sample[mask], minm, maxm, out=data_sample[mask])

    return data_sample


def augment_brightness_additive(data_sample, mu: float, sigma: float, per_channel: bool = True,
                                p_per_channel: float = 1.):
    """
    data_sample must have shape (c, x, y(, z)))
    :param data_sample: 
    :param mu: 
    :param sigma: 
    :param per_channel: 
    :param p_per_channel: 
    :return: 
    """
    size = data_sample.shape[0]
    if per_channel:
        rnd_nb = np.random.normal(mu, sigma, size=size)
    else:
        rnd_nb = np.repeat(np.random.normal(mu, sigma), size)
    rnd_nb[np.random.uniform(size=size) > p_per_channel] = 0.0
    data_sample += reverse_broadcast(rnd_nb, get_broadcast_axes(data_sample.ndim))
    return data_sample


def setup_augment_brightness_multiplicative(per_channel: bool, batched: bool, shape: Tuple[int, ...]):
    if per_channel:
        if batched:
            return shape[:2] + (1,) * (len(shape) - 2)
        return (shape[0],) + (1,) * (len(shape) - 1)
    if batched:
        return (shape[0],) + (1,) * (len(shape) - 1)
    return (1,) * len(shape)


def augment_brightness_multiplicative(data_sample, multiplier_range=(0.5, 2), per_channel=True, batched=False):
    size = setup_augment_brightness_multiplicative(per_channel, batched, data_sample.shape)
    data_sample *= np.random.uniform(multiplier_range[0], multiplier_range[1], size=size)
    return data_sample


def augment_gamma(data_sample, gamma_range=(0.5, 2), invert_image=False, epsilon=1e-7, per_channel=False,
                  retain_stats: Union[bool, Callable[[], bool]] = False):
    if invert_image:
        data_sample = - data_sample

    if not per_channel:
        retain_stats = retain_stats() if callable(retain_stats) else retain_stats
        if retain_stats:
            mn = data_sample.mean()
            sd = data_sample.std()
        if gamma_range[0] < 1 and np.random.random() < 0.5:
            gamma = np.random.uniform(gamma_range[0], 1)
        else:
            gamma = np.random.uniform(max(gamma_range[0], 1), gamma_range[1])
        minm = data_sample.min()
        rnge = data_sample.max() - minm
        data_sample = np.power(((data_sample - minm) / float(rnge + epsilon)), gamma) * rnge + minm
        if retain_stats:
            data_sample -= data_sample.mean()
            data_sample *= sd / (data_sample.std() + 1e-8)
            data_sample += mn
    else:
        shape_0 = data_sample.shape[0]
        gamma = []
        gamma_l = max(gamma_range[0], 1)
        for i in range(shape_0):
            if gamma_range[0] < 1 and np.random.random() < 0.5:
                gamma.append(np.random.uniform(gamma_range[0], 1))
            else:
                gamma.append(np.random.uniform(gamma_l, gamma_range[1]))
        gamma = np.array(gamma)

        axes = tuple(range(1, data_sample.ndim))

        if callable(retain_stats):
            retain_stats = [retain_stats() for _ in range(shape_0)]
        else:
            retain_stats = [retain_stats] * shape_0
        retain_stats_here = any(retain_stats)
        if retain_stats_here:
            mn = data_sample[retain_stats].mean(axis=axes, keepdims=True)
            sd = data_sample[retain_stats].mean(axis=axes, keepdims=True)

        minm = data_sample.min(axis=axes, keepdims=True)
        rnge = data_sample.max(axis=axes, keepdims=True) - minm + epsilon

        broadcast_axes = get_broadcast_axes(data_sample.ndim)
        gamma = reverse_broadcast(gamma, broadcast_axes)
        data_sample = np.power((data_sample - minm) / rnge, gamma) * rnge + minm

        if retain_stats_here:
            data_sample[retain_stats] -= data_sample[retain_stats].mean(axis=axes, keepdims=True)
            data_sample[retain_stats] *= sd / (data_sample[retain_stats].std(axis=axes, keepdims=True) + 1e-8)
            data_sample[retain_stats] += mn

    if invert_image:
        data_sample = - data_sample
    return data_sample


def augment_illumination(data, white_rgb):
    idx = np.random.choice(len(white_rgb), data.shape[0])
    for sample in range(data.shape[0]):
        _, img = general_cc_var_num_channels(data[sample], 0, 5, 0, None, 1., 7, False)
        rgb = np.array(white_rgb[idx[sample]]) * np.sqrt(3)
        for c in range(data[sample].shape[0]):
            data[sample, c] = img[c] * rgb[c]
    return data


def augment_PCA_shift(data, U, s, sigma=0.2):
    for sample in range(data.shape[0]):
        data[sample] = illumination_jitter(data[sample], U, s, sigma)
        data[sample] -= data[sample].min()
        data[sample] /= data[sample].max()
    return data
