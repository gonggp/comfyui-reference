import os
import sys
import os.path as osp

import torch
from torchvision.transforms import ToPILImage, ToTensor
from .prepare_latent_masks import prepare_latent_masks_with_split, prepare_latent_masks_with_segment


def latents_shape(height, width, mask_rps):
    whs = {}
    mask_rp_res = {}

    to_pil = ToPILImage()
    to_tensor = ToTensor()

    new_height = height
    new_width = width
    whs[new_height * new_width] = [new_height , new_width]
    res_mask_rps = []

    mask_background = torch.ones((new_height, new_width), dtype=torch.float16)

    for idx, mask_rp in enumerate(mask_rps):
        resize_mask_rp = to_pil(mask_rp.to(torch.uint8)*255).resize((new_width, new_height))
        resize_mask_rp.save(f'mask_rp_{idx}.jpg')
        #print(mask_rp.shape)
        #mask_rp_norm = F.interpolate(mask_rp, size=(new_height, new_width), mode='nearest')
        #mask_rp_norm = mask_rp.resize((new_width,new_height))
        res_mask_rps.append(mask_rp.to("cuda").to(torch.float16))
        mask_background = mask_background.to("cuda").to(torch.float16) - mask_rp.to("cuda").to(torch.float16)
    resize_mask_rp = to_pil(mask_background.to(torch.uint8)*255)
    resize_mask_rp.save('mask_rp_base.jpg')
    res_mask_rps.insert(0, mask_background.to("cuda").to(torch.float16))
    mask_rp_res[new_height * new_width] = res_mask_rps

    for i in range(7):
        if new_height%2 ==0:
            new_height = new_height//2
            new_width = new_width //2
        else:
            new_height = (new_height+1)//2
            new_width = (new_width+1) //2
        area = new_height * new_width
        #print(new_height, new_width, area)
        whs[area] = [new_height , new_width]
        res_mask_rps = []
        mask_background = torch.ones((new_height, new_width), dtype=torch.float16)
        for mask_rp in mask_rps:
            resize_mask_rp = to_pil(mask_rp.to(torch.uint8)*255).resize((new_width, new_height))
            mask_rp_norm = to_tensor(resize_mask_rp).reshape((new_height, new_width))
            res_mask_rps.append(mask_rp_norm.to("cuda").to(torch.float16))
            mask_background = mask_background.to("cuda").to(torch.float16) - mask_rp_norm.to("cuda").to(torch.float16)
        res_mask_rps.insert(0, mask_background.to("cuda").to(torch.float16))
        mask_rp_res[area] =  res_mask_rps
    return whs, mask_rp_res

def roi_mask_proc(roi_mask_attrs: dict):
    height = roi_mask_attrs['height']
    width = roi_mask_attrs['width']
    roi_mask = roi_mask_attrs['roi_mask']
    merge_weight = roi_mask_attrs['merge_weight']
    rp_bbox = roi_mask_attrs['rp_bbox']
    rp_split_ratio = roi_mask_attrs['rp_split_ratio']

    latents_w = width//8
    latents_h = height//8

    try:
        mask_rp_at_second_stage, _, _ = prepare_latent_masks_with_segment(
            is_row=True if 0 == 0 else False,
            latent_h = latents_h,
            latent_w = latents_w,
            latent_split=rp_split_ratio,
            rp_bboxs=rp_bbox,
            rp_mask_url=roi_mask,
        )

        whs, mask_rp_res = latents_shape(latents_h, latents_w, mask_rp_at_second_stage)
    except Exception as err:
        print("warning roi mask error: {}".format(err))
        whs = {}
        mask_rp_res = {}


    return whs, mask_rp_res

