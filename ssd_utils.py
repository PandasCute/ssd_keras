"""Some utils for SSD."""

import numpy as np
import tensorflow as tf


def softmax(x):
    """Softmax applied to las axix of tensor.

    # Argoments
        x: Numpy tensor to process
    # Return
        sm: Processed numpy tensor
    """
    sm = np.exp(x - x.max(axis=-1, keepdims=True))
    sm /= sm.sum(axis=-1, keepdims=True)
    return sm


def decode_boxes(mbox_loc, mbox_priorbox, variances):
    """Convert bboxes from local predictions to shifted priors.

    # Arguments
        mbox_loc: Numpy array of predicted locations.
        mbox_priorbox: Numpy array of prior boxes.
        variances: Numpy array of variances.

    # Return:
        decode_bbox: Shifted priors.
    """
    prior_width = mbox_priorbox[:, 2] - mbox_priorbox[:, 0]
    prior_height = mbox_priorbox[:, 3] - mbox_priorbox[:, 1]
    prior_center_x = 0.5 * (mbox_priorbox[:, 2] + mbox_priorbox[:, 0])
    prior_center_y = 0.5 * (mbox_priorbox[:, 3] + mbox_priorbox[:, 1])
    decode_bbox_center_x = mbox_loc[:, 0] * prior_width * variances[:, 0]
    decode_bbox_center_x += prior_center_x
    decode_bbox_center_y = mbox_loc[:, 1] * prior_width * variances[:, 1]
    decode_bbox_center_y += prior_center_y
    decode_bbox_width = np.exp(mbox_loc[:, 2] * variances[:, 2])
    decode_bbox_width *= prior_width
    decode_bbox_height = np.exp(mbox_loc[:, 3] * variances[:, 3])
    decode_bbox_height *= prior_height
    decode_bbox_xmin = decode_bbox_center_x - 0.5 * decode_bbox_width
    decode_bbox_ymin = decode_bbox_center_y - 0.5 * decode_bbox_height
    decode_bbox_xmax = decode_bbox_center_x + 0.5 * decode_bbox_width
    decode_bbox_ymax = decode_bbox_center_y + 0.5 * decode_bbox_height
    decode_bbox = np.concatenate((decode_bbox_xmin[:, None],
                                  decode_bbox_ymin[:, None],
                                  decode_bbox_xmax[:, None],
                                  decode_bbox_ymax[:, None]), axis=-1)
    decode_bbox = np.minimum(np.maximum(decode_bbox, 0.0), 1.0)
    return decode_bbox


def detection_out(mbox_loc, mbox_conf, mbox_priorbox, num_classes=21,
                  background_label_id=0, nms_thresh=0.45, top_k=400,
                  keep_top_k=200, confidence_threshold=0.01):
    """Do non maximum suppression (nms) on prediction results.

    # Arguments
        mbox_loc: Numpy array of predicted locations.
        mbox_conf: Numpy array of predicted confidences.
        mbox_priorbox: Numpy array of prior boxes.
        num_classes: Number of classes for prediction.
        background_label_id: Label of background class.
        nms_thresh: Nms threshold.
        top_k: Number of total bboxes to be kept per image after nms step.
        keep_top_k: Number of total bboxes to be kept per image after nms step.
        confidence_threshold: Only consider detections,
            whose confidences are larger than a threshold.
    """
    config = tf.ConfigProto(device_count={'GPU': 0})
    mbox_loc = mbox_loc.reshape(-1, mbox_loc.shape[1] // 4, 4)
    variances = mbox_priorbox[:, 1, :].reshape(-1, mbox_priorbox.shape[2] // 4,
                                               4)
    mbox_priorbox = mbox_priorbox[:, 0, :].reshape(-1,
                                                   mbox_priorbox.shape[2] // 4,
                                                   4)
    mbox_conf = mbox_conf.reshape(-1, mbox_conf.shape[1] // num_classes,
                                  num_classes)
    mbox_conf = softmax(mbox_conf)
    predictions = []
    for i in range(len(mbox_loc)):
        predictions.append([])
        decode_bbox = decode_boxes(mbox_loc[i], mbox_priorbox[i], variances[i])
        tf.reset_default_graph()
        boxes = tf.placeholder(dtype='float32', shape=(None, 4))
        scores = tf.placeholder(dtype='float32', shape=(None,))
        nms = tf.image.non_max_suppression(boxes, scores, top_k,
                                           iou_threshold=nms_thresh)
        sess = tf.Session(config=config)
        for c in range(num_classes):
            if c == background_label_id:
                continue
            c_confs = mbox_conf[i, :, c]
            c_confs_m = c_confs > confidence_threshold
            if len(c_confs[c_confs_m]) > 0:
                boxes_to_process = decode_bbox[c_confs_m]
                confs_to_process = c_confs[c_confs_m]
                idx = sess.run(nms, feed_dict={boxes: boxes_to_process,
                                               scores: confs_to_process})
                good_boxes = boxes_to_process[idx]
                confs = confs_to_process[idx][:, None]
                labels = c * np.ones((len(idx), 1))
                c_pred = np.concatenate((labels, confs, good_boxes), axis=1)
                predictions[-1].extend(c_pred)
        predictions[-1] = np.array(predictions[-1])
        argsort = np.argsort(predictions[-1][:, 1])[::-1]
        predictions[-1] = predictions[-1][argsort]
        predictions[-1] = predictions[-1][:keep_top_k]
    return predictions
