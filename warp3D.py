#!/usr/bin/env python3
"""
Implemention of Spatial Transformation Network
"""
import tensorflow as tf
import numpy as np
from config import get_config

config = get_config(is_train=True)

def batch_warp3d(imgs, mappings, marks, base_map):
    """
    warp image using mapping function
    I(x) -> I(phi(x))
    phi: mapping function

    Parameters
    ----------
    imgs : tf.Tensor
        images to be warped
        [n_batch, xlen, ylen, zlen, n_channel]
    mapping : tf.Tensor
        grids representing mapping function
        [n_batch, xlen, ylen, zlen, 3]
    marks : tf.Tensor
        [n_batch, config.num_mark, 3]
    Returns
    -------
    output : tf.Tensor
        warped images
        [n_batch, xlen, ylen, zlen, n_channel]
    """
    n_batch = tf.shape(imgs)[0]
    coords = tf.reshape(mappings, [n_batch, 3, -1])
    x_coords = tf.slice(coords, [0, 0, 0], [-1, 1, -1])
    y_coords = tf.slice(coords, [0, 1, 0], [-1, 1, -1])
    z_coords = tf.slice(coords, [0, 2, 0], [-1, 1, -1])
    x_coords_flat = tf.reshape(x_coords, [-1])
    y_coords_flat = tf.reshape(y_coords, [-1])
    z_coords_flat = tf.reshape(z_coords, [-1])

    marks = tf.transpose(marks, [0, 2, 1])
    marks = tf.reshape(marks, [n_batch, 3, -1])
    output = _interpolate3d(imgs, x_coords_flat, y_coords_flat, z_coords_flat, marks)
    return output

def _repeat(base_indices, n_repeats):
    base_indices = tf.matmul(
        tf.reshape(base_indices, [-1, 1]),
        tf.ones([1, n_repeats], dtype='int32'))
    return tf.reshape(base_indices, [-1])

def _interpolate3d(imgs, x, y, z, marks):
    n_batch = tf.shape(imgs)[0]
    xlen = tf.shape(imgs)[1]
    ylen = tf.shape(imgs)[2]
    zlen = tf.shape(imgs)[3]
    n_channel = tf.shape(imgs)[4]

    x = tf.to_float(x)
    y = tf.to_float(y)
    z = tf.to_float(z)
    xlen_f = tf.to_float(xlen)
    ylen_f = tf.to_float(ylen)
    zlen_f = tf.to_float(zlen)
    zero = tf.zeros([], dtype='int32')
    max_x = tf.cast(xlen - 1, 'int32')
    max_y = tf.cast(ylen - 1, 'int32')
    max_z = tf.cast(zlen - 1, 'int32')

    # scale indices from [-1, 1] to [0, xlen/ylen/zlen]
    x = (x + 1.) * (xlen_f - 1.) * 0.5
    y = (y + 1.) * (ylen_f - 1.) * 0.5
    z = (z + 1.) * (zlen_f - 1.) * 0.5

    # do sampling
    x0 = tf.cast(tf.floor(x), 'int32')
    x1 = x0 + 1
    y0 = tf.cast(tf.floor(y), 'int32')
    y1 = y0 + 1
    z0 = tf.cast(tf.floor(z), 'int32')
    z1 = z0 + 1

    x0 = tf.clip_by_value(x0, zero, max_x)
    x1 = tf.clip_by_value(x1, zero, max_x)
    y0 = tf.clip_by_value(y0, zero, max_y)
    y1 = tf.clip_by_value(y1, zero, max_y)
    z0 = tf.clip_by_value(z0, zero, max_z)
    z1 = tf.clip_by_value(z1, zero, max_z)
    base = _repeat(tf.range(n_batch) * xlen * ylen * zlen,
                   xlen * ylen * zlen)
    base_x0 = base + x0 * ylen * zlen
    base_x1 = base + x1 * ylen * zlen
    base00 = base_x0 + y0 * zlen
    base01 = base_x0 + y1 * zlen
    base10 = base_x1 + y0 * zlen
    base11 = base_x1 + y1 * zlen
    index000 = base00 + z0
    index001 = base00 + z1
    index010 = base01 + z0
    index011 = base01 + z1
    index100 = base10 + z0
    index101 = base10 + z1
    index110 = base11 + z0
    index111 = base11 + z1

    # use indices to lookup pixels in the flat image and restore
    # n_channel dim
    imgs_flat = tf.reshape(imgs, [-1, n_channel])
    imgs_flat = tf.to_float(imgs_flat)
    I000 = tf.gather(imgs_flat, index000)
    I001 = tf.gather(imgs_flat, index001)
    I010 = tf.gather(imgs_flat, index010)
    I011 = tf.gather(imgs_flat, index011)
    I100 = tf.gather(imgs_flat, index100)
    I101 = tf.gather(imgs_flat, index101)
    I110 = tf.gather(imgs_flat, index110)
    I111 = tf.gather(imgs_flat, index111)

    # and finally calculate interpolated values
    dx = x - tf.to_float(x0)
    dy = y - tf.to_float(y0)
    dz = z - tf.to_float(z0)
    w000 = tf.expand_dims((1. - dx) * (1. - dy) * (1. - dz), 1)
    w001 = tf.expand_dims((1. - dx) * (1. - dy) * dz, 1)
    w010 = tf.expand_dims((1. - dx) * dy * (1. - dz), 1)
    w011 = tf.expand_dims((1. - dx) * dy * dz, 1)
    w100 = tf.expand_dims(dx * (1. - dy) * (1. - dz), 1)
    w101 = tf.expand_dims(dx * (1. - dy) * dz, 1)
    w110 = tf.expand_dims(dx * dy * (1. - dz), 1)
    w111 = tf.expand_dims(dx * dy * dz, 1)
    output = tf.add_n([w000 * I000, w001 * I001, w010 * I010, w011 * I011,
                       w100 * I100, w101 * I101, w110 * I110, w111 * I111])

    # reshape
    output = tf.reshape(output, [n_batch, xlen, ylen, zlen, n_channel])

    # Process landmarks
    x_marks = tf.slice(marks, [0, 0, 0], [-1, 1, -1])
    y_marks = tf.slice(marks, [0, 1, 0], [-1, 1, -1])
    z_marks = tf.slice(marks, [0, 2, 0], [-1, 1, -1])
    x_marks_flat = tf.reshape(x_marks, [-1])
    y_marks_flat = tf.reshape(y_marks, [-1])
    z_marks_flat = tf.reshape(z_marks, [-1])
    base = _repeat(tf.range(n_batch) * xlen * ylen * zlen, config.num_mark)
    mark_index = base + x_marks_flat * ylen * zlen + y_marks_flat * zlen + z_marks_flat
    x_transformed = tf.reshape(tf.gather(x, mark_index), [n_batch, -1, 1])
    y_transformed = tf.reshape(tf.gather(y, mark_index), [n_batch, -1, 1])
    z_transformed = tf.reshape(tf.gather(z, mark_index), [n_batch, -1, 1])
    marks_transformed = tf.concat([x_transformed, y_transformed, z_transformed], 2)
    return output, marks_transformed, x, y, z
