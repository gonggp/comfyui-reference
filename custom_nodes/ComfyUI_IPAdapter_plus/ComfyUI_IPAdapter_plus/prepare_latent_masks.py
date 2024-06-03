import logging
import math
import cv2
import os

from shutil import copyfile
from typing import (List, Optional)

import torch
import torch.nn.functional as F
import torchvision
from torchvision.utils import save_image

from diffusers.utils import load_image

import sys

dir_path = os.path.dirname(os.path.realpath(__file__))
dir_path = "/".join(dir_path.split('/')[0:-2])
print(dir_path)
sys.path.insert(0, os.path.join(dir_path, 'magic_common'))

from magic.utils.fuzzy_download import fuzzy_download_to_file


def prepare_mask_boundaries(mask=None):
    nonzero_indices = torch.nonzero(mask)

    #
    min_row = torch.min(nonzero_indices[:, 0])
    max_row = torch.max(nonzero_indices[:, 0])
    min_col = torch.min(nonzero_indices[:, 1])
    max_col = torch.max(nonzero_indices[:, 1])

    return [
        min_col.item(),
        min_row.item(),
        max_col.item(),
        max_row.item(),
    ]
    # return [
    #     min_col.item(),
    #     max_col.item(),
    #     min_row.item(),
    #     max_row.item(),
    # ]

def prepare_better_rp_bboxes(
    is_row: bool = True,
    bboxes: List = [],
    multiplier: float = 1.1,
):
    rp_bboxes_better = []
    bboxes_have_head = []
    bboxes_have_no_head = []

    for _, bbox in enumerate(bboxes):
        bboxes_have_head.append((bbox[0] if is_row else bbox[1], bbox))
    bboxes_have_head = sorted(bboxes_have_head, key=lambda x: x[0])

    for _, bbox in enumerate(bboxes_have_head):
        bboxes_have_no_head.append(bbox[1])
    my_bboxes = bboxes_have_no_head

    for my_bbox in my_bboxes:
        my_bbox[2:] = [x * multiplier for x in my_bbox[2:]]

        my_tl_x = max(0, min(my_bbox[0] - my_bbox[2] / 2, 1))
        my_tl_y = max(0, min(my_bbox[1] - my_bbox[3] / 2, 1))
        my_rb_x = max(0, min(my_bbox[0] + my_bbox[2] / 2, 1))
        my_rb_y = max(0, min(my_bbox[1] + my_bbox[3] / 2, 1))

        norm_x = (my_tl_x + my_rb_x) / 2
        norm_y = (my_tl_y + my_rb_y) / 2
        norm_w = (my_rb_x - my_tl_x)
        norm_h = (my_rb_y - my_tl_y)

        rp_bboxes_better.append([norm_x, norm_y, norm_w, norm_h])

    return rp_bboxes_better

def prepare_latent_masks_with_split(
    is_row: bool = True,
    latent_h: Optional[int] = None,
    latent_w: Optional[int] = None,
    latent_split: float = 0.5,
):
    #
    mask_zeros = torch.zeros((latent_h, latent_w), dtype=torch.int)
    mask_zeros_flip = torch.zeros((latent_h, latent_w), dtype=torch.int)

    #
    if is_row:
        mid_w = math.floor(latent_split * latent_w + 0.5)
        mask_zeros[:, :mid_w] = 1
        mask_zeros_flip[:, mid_w:] = 1
    else:
        mid_h = math.floor(latent_split * latent_h + 0.5)
        mask_zeros[:mid_h, :] = 1
        mask_zeros_flip[mid_h:, :] = 1

    mask_twins = [mask_zeros, mask_zeros_flip]

    for _u, _mask in enumerate(mask_twins):
        save_image(_mask.float(), f'mask_twins_split_{_u}.png')

    return mask_twins

def prepare_latent_masks_with_segment(
    is_row: bool = True,
    latent_h: Optional[int] = None,
    latent_w: Optional[int] = None,
    latent_split: float = 0.5,
    rp_bboxs: List = [],
    rp_mask_url: Optional[str] = None,
):
    mask_segments = []
    mask_twins = []
    mask_expand = []
    print("preprare-test: {}".format(rp_mask_url))

    #
    mask_zeros = torch.zeros((latent_h, latent_w), dtype=torch.int)
    mask_zeros_flip = torch.zeros((latent_h, latent_w), dtype=torch.int)

    #
    if is_row:
        mid_w = math.floor(latent_split * latent_w + 0.5)
        mask_zeros[:, :mid_w] = 1
        mask_zeros_flip[:, mid_w:] = 1
    else:
        mid_h = math.floor(latent_split * latent_h + 0.5)
        mask_zeros[:mid_h, :] = 1
        mask_zeros_flip[mid_h:, :] = 1

    #
    mask_file = '/tmp/prepare_latent_masks_with_segment.png'

    mask_num = 0
    mask_vae = []
    mask_uid = []

    #
    if rp_mask_url:
        logging.info('prepare_latent_masks_with_segment()->Info():rp_mask_url={}'.format(rp_mask_url))
        print('prepare_latent_masks_with_segment()->Info():rp_mask_url={}'.format(rp_mask_url))
        try:
            if os.path.isfile(rp_mask_url):
                copyfile(rp_mask_url, mask_file)
            else:
                print("fuzzy_download_to_file: {}".format(rp_mask_url))
                fuzzy_download_to_file(
                    uri=rp_mask_url, local_filepath=mask_file, region='us-east-1',
                )

            mask = torch.from_numpy(
                cv2.imread(mask_file, cv2.IMREAD_GRAYSCALE)
            )

            mask_vae = F.interpolate(
                mask.unsqueeze(0).unsqueeze(0), (latent_h, latent_w), mode="nearest",
            ).squeeze(0).squeeze(0)

            mask_uid, _ = torch.unique(mask_vae, return_counts=True)
        except Exception as e:
            rp_mask_url = None
            logging.exception('prepare_latent_masks_with_segment()->Exception():rp_mask_url={}'.format(rp_mask_url))
            print('prepare_latent_masks_with_segment()->Exception():rp_mask_url={}'.format(rp_mask_url))
            # raise FileNotFoundError(f'The file does not exist: {e}.')

    #
    mask_uid = mask_uid[1:]
    mask_num = len(mask_uid)

    print("s3 don2: {}".format(rp_mask_url))

    #
    if rp_mask_url and mask_num > 0:
        #
        kval_main = {}

        #
        for _, bbox in enumerate(rp_bboxs):
            tl_x = math.floor((bbox[0] - bbox[2] / 2) * latent_w + 0.5)
            tl_y = math.floor((bbox[1] - bbox[3] / 2) * latent_h + 0.5)
            rb_x = math.floor((bbox[0] + bbox[2] / 2) * latent_w + 0.5)
            rb_y = math.floor((bbox[1] + bbox[3] / 2) * latent_h + 0.5)

            tl_x = max(0, min(tl_x, latent_w - 1))
            tl_y = max(0, min(tl_y, latent_h - 1))
            rb_x = max(0, min(rb_x, latent_w - 1))
            rb_y = max(0, min(rb_y, latent_h - 1))

            det_bbox = [tl_x, tl_y, rb_x, rb_y]

            latent_zeros = torch.zeros((latent_h, latent_w), dtype=torch.int)
            latent_zeros[tl_y:rb_y, tl_x:rb_x] = 1
            latent_sum = torch.sum(latent_zeros).item()

            mask_max = 0
            mask_max_score = 0
            mask_bbox = None
            mask_overlaped = False

            for _, mask_u in enumerate(mask_uid):
                mask_this = (mask_vae == mask_u) & latent_zeros
                mask_score = torch.sum(mask_this).item() / latent_sum
                if mask_score > mask_max_score:
                    mask_max = mask_u.tolist()
                    mask_max_score = mask_score
                    mask_bbox = prepare_mask_boundaries(mask_this)
                    mask_overlaped = True
                logging.info('prepare_latent_masks_with_segment()->Match():[det_bbox={}, mask={}, mask_bbox={}, score={}]'.format(det_bbox, mask_u, mask_bbox, mask_score))
                print('prepare_latent_masks_with_segment()->Match():[det_bbox={}, mask={}, mask_bbox={}, score={}]'.format(det_bbox, mask_u, mask_bbox, mask_score))

            if mask_overlaped:
                kval_main.setdefault(mask_max, [])
                kval_main[mask_max].append((mask_max_score, det_bbox, mask_bbox))

        # kval_main = { mask_u: (mask_score, expand_bbox) }
        kval_lite = {}
        for _key, _tree in kval_main.items():
            score = 0
            expand_bbox = None
            for _tuple in _tree:
                if _tuple[0] > score:
                    score = _tuple[0]

                    expand_bbox = torch.tensor([_tuple[1], _tuple[2]]).reshape(2, -1)
                    min_elem, _ = torch.min(expand_bbox, dim=0)
                    max_elem, _ = torch.max(expand_bbox, dim=0)
                    expand_bbox = [
                        min_elem[0].item(), min_elem[1].item(), max_elem[2].item(), max_elem[3].item()
                    ]

            kval_lite[_key] = (score, expand_bbox)
        kval_main = kval_lite

        #
        for k_, tuple_ in kval_main.items():
            #
            plot_zeros = torch.zeros((latent_h, latent_w), dtype=torch.int)
            #
            plot_zeros[mask_vae == k_] = 16
            #
            tl_x_, tl_y_, rb_x_, rb_y_ = tuple_[1]
            #
            plot_zeros[tl_y_:rb_y_, tl_x_] = 255
            plot_zeros[tl_y_:rb_y_, rb_x_] = 255
            plot_zeros[tl_y_, tl_x_:rb_x_] = 255
            plot_zeros[rb_y_, tl_x_:rb_x_] = 255
            #
            # save_image(plot_zeros.float(), f'plot_mask_{k_}_with_expand_bbox.jpg')

        # kval_mask_main = { mask_u: expand_mask }
        kval_mask_main = {}
        for _key, _tuple in kval_main.items():
            tl_x_, tl_y_, rb_x_, rb_y_ = _tuple[1]

            _pad_h = math.floor((rb_y_ - tl_y_) * 0.1 + 0.5)
            _pad_w = math.floor((rb_x_ - tl_x_) * 0.1 + 0.5)

            _tl_x = tl_x_ if tl_x_ > _pad_w else 0
            _tl_y = tl_y_ if tl_y_ > _pad_h else 0
            _rb_x = rb_x_ if (latent_w - rb_x_) > _pad_w else latent_w
            _rb_y = rb_y_ if (latent_h - rb_y_) > _pad_h else latent_h

            expand_mask = torch.zeros((latent_h, latent_w), dtype=torch.int)
            expand_mask[_tl_y:_rb_y, _tl_x:_rb_x] = 1

            kval_mask_main[_key] = expand_mask

        #
        mask_key_u = list(kval_mask_main.keys())
        mask_key_num = len(mask_key_u)
        #
        if mask_key_num >= 1 and mask_key_num == len(rp_bboxs):
            mask_and = (mask_vae == mask_key_u[0]) & mask_zeros
            mask_and_flip = (mask_vae == mask_key_u[0]) & mask_zeros_flip

            expand_mask = kval_mask_main[mask_key_u[0]]
            if mask_key_num > 1:
                expand_mask1 = kval_mask_main[mask_key_u[1]]

            if torch.sum(mask_and) > torch.sum(mask_and_flip):
                expand_mask = expand_mask & mask_zeros
                if mask_key_num > 1:
                    expand_mask1 = expand_mask1 & mask_zeros_flip
            else:
                expand_mask = expand_mask & mask_zeros_flip
                if mask_key_num > 1:
                    expand_mask1 = expand_mask1 & mask_zeros

            mask_segment = (mask_vae == mask_key_u[0])
            mask_mixture = mask_segment | expand_mask

            mask_mixture_4d = mask_mixture.unsqueeze(0).unsqueeze(0)
            mask_mixture_4d = F.max_pool2d(mask_mixture_4d, kernel_size=5, stride=1, padding=2)
            mask_mixture_expand = mask_mixture_4d.squeeze(0).squeeze(0)

            mask_segments.append(mask_segment)

            if mask_key_num > 1:
                mask_segment1 = (mask_vae == mask_key_u[1])
                mask_mixture1 = mask_segment1 | expand_mask1

                mask_mixture1_4d = mask_mixture1.unsqueeze(0).unsqueeze(0)
                mask_mixture1_4d = F.max_pool2d(mask_mixture1_4d, kernel_size=5, stride=1, padding=2)
                mask_mixture1_expand = mask_mixture1_4d.squeeze(0).squeeze(0)

                mask_segments.append(mask_segment1)

            if mask_key_num > 1:
                mask_mixture[mask_vae == mask_key_u[1]] = 0
                mask_mixture1[mask_vae == mask_key_u[0]] = 0

                mask_mixture_expand[mask_vae == mask_key_u[1]] = 0
                mask_mixture1_expand[mask_vae == mask_key_u[0]] = 0
            else:
                mask_mixture1 = torch.zeros((latent_h, latent_w), dtype=torch.int)
                mask_mixture1 = (mask_mixture == 0) & mask_mixture1

                mask_mixture1_expand = torch.zeros((latent_h, latent_w), dtype=torch.int)
                mask_mixture1_expand = (mask_mixture_expand == 0) & mask_mixture1_expand

            # mask_twins = [mask_mixture, mask_mixture1]
            mask_twins = [mask_mixture_expand, mask_mixture1_expand]
        else:
            mask_segments = mask_twins = [mask_zeros, mask_zeros_flip]
    else:
        mask_segments = mask_twins = [mask_zeros, mask_zeros_flip]

    # for _u, _mask in enumerate(mask_twins):
    #     save_image(_mask.float(), f'mask_twins_segment_{_u}.png')

    # for _u, _mask in enumerate(mask_segments):
    #     save_image(_mask.float(), f'mask_seg_segment_{_u}.png')

    print("done-s3")

    return mask_segments, mask_twins, mask_expand
