import torch
import math
import torch.nn.functional as F
from comfy.ldm.modules.attention import optimized_attention
from .utils import tensor_to_size


def latents_fusion(hidden_states, whs, mask_rp_res, ip_rp_weight):
    tp_hidden_states_cond, tp_hidden_states_uncond, ip_hidden_states_cond ,ip_hidden_states_uncond = hidden_states.chunk(4)
    height, width = whs[tp_hidden_states_cond.shape[1]]
    mask_rps = mask_rp_res[tp_hidden_states_cond.shape[1]]
    
    c = tp_hidden_states_cond.shape[2]

    mask_base = (
        mask_rps[0]
        .unsqueeze(0)
        .unsqueeze(-1)
        .repeat(1,1,1,c)
    )
    tp_hidden_states_cond = tp_hidden_states_cond.reshape(1,  height, width, c)
    ip_hidden_states_cond = ip_hidden_states_cond.reshape(1,  height, width, c)

    tp_hidden_states_uncond = tp_hidden_states_uncond.reshape(1, height, width, c)
    ip_hidden_states_uncond = ip_hidden_states_uncond.reshape(1, height, width, c)

    ip_hidden_states_cond_fuse = torch.zeros((1, height, width, c), dtype = torch.float16, device='cuda')
    ip_hidden_states_uncond_fuse = torch.zeros((1, height, width, c), dtype = torch.float16, device='cuda')
    for idx in range(1, len(mask_rps)):
        mask_rp = (
            mask_rps[idx]
            .unsqueeze(0)
            .unsqueeze(-1)
            .repeat(1,1,1,c)
        )
        ip_hidden_states_cond_fuse = ip_hidden_states_cond_fuse + ip_hidden_states_cond * mask_rp
        ip_hidden_states_uncond_fuse = ip_hidden_states_uncond_fuse + ip_hidden_states_uncond* mask_rp
    
    ip_hidden_states_cond_fuse = ip_hidden_states_cond_fuse + tp_hidden_states_cond * mask_base 
    ip_hidden_states_uncond_fuse = ip_hidden_states_uncond_fuse + tp_hidden_states_uncond * mask_base

    hidden_states_cond = tp_hidden_states_cond * (1- ip_rp_weight) + ip_rp_weight * ip_hidden_states_cond_fuse
    hidden_states_cond = hidden_states_cond.reshape(1, -1 ,c)

    hidden_states_uncond = tp_hidden_states_uncond * (1- ip_rp_weight) +  ip_rp_weight * ip_hidden_states_uncond_fuse 
    hidden_states_uncond = hidden_states_uncond.reshape(1, -1 ,c)

    tp_hidden_states_uncond = tp_hidden_states_uncond.reshape(1, -1, c)
    ip_hidden_states_uncond = ip_hidden_states_uncond.reshape(1, -1, c)

    hidden_states = torch.cat([
        hidden_states_cond,
        hidden_states_uncond,
    ])
    return hidden_states


class Attn2Replace:
    def __init__(self, callback=None, **kwargs):
        self.callback = [callback]
        self.kwargs = [kwargs]
    
    def add(self, callback, **kwargs):          
        self.callback.append(callback)
        self.kwargs.append(kwargs)

        for key, value in kwargs.items():
            setattr(self, key, value)

    def __call__(self, q, k, v, extra_options):
        dtype = q.dtype
        out = optimized_attention(q, k, v, extra_options["n_heads"])
        sigma = extra_options["sigmas"].detach().cpu()[0].item() if 'sigmas' in extra_options else 999999999.9

        for i, callback in enumerate(self.callback):
            roi_mask_dict = self.kwargs[i].get('roi_mask_dict', {})
            if roi_mask_dict == {}:
                if sigma <= self.kwargs[i]["sigma_start"] and sigma >= self.kwargs[i]["sigma_end"]:
                    out = out + callback(out, q, k, v, extra_options, **self.kwargs[i])
            else:
                ip_rp_weight = roi_mask_dict.get("ip_rp_weight", 1.0)
                whs = roi_mask_dict.get("whs", {})
                mask_rp_res = roi_mask_dict.get("mask_rp_res", {})
                if sigma <= self.kwargs[i]["sigma_start"] and sigma >= self.kwargs[i]["sigma_end"]:
                    #out = out + callback(out, q, k, v, extra_options, **self.kwargs[i]) 
                    out_ip =  callback(out, q, k, v, extra_options, **self.kwargs[i]) 
                    out_merge = torch.cat([out, out_ip])
                    out = latents_fusion(out_merge, whs, mask_rp_res, ip_rp_weight)
        
        return out.to(dtype=dtype)

def ipadapter_attention(
        out, 
        q, 
        k, 
        v, 
        extra_options, 
        module_key='', 
        ipadapter=None, 
        weight=1.0, 
        cond=None, 
        cond_alt=None, 
        uncond=None, 
        weight_type="linear", 
        mask=None, 
        sigma_start=0.0, 
        sigma_end=1.0, 
        unfold_batch=False, 
        embeds_scaling='V only', 
        roi_mask_dict = {},
        **kwargs
):
    dtype = q.dtype
    cond_or_uncond = extra_options["cond_or_uncond"]
    block_type = extra_options["block"][0]
    #block_id = extra_options["block"][1]
    t_idx = extra_options["transformer_index"]
    layers = 11 if '101_to_k_ip' in ipadapter.ip_layers.to_kvs else 16
    k_key = module_key + "_to_k_ip"
    v_key = module_key + "_to_v_ip"

    # extra options for AnimateDiff
    ad_params = extra_options['ad_params'] if "ad_params" in extra_options else None

    b = q.shape[0]
    seq_len = q.shape[1]
    batch_prompt = b // len(cond_or_uncond)
    _, _, oh, ow = extra_options["original_shape"]

    if weight_type == 'ease in':
        weight = weight * (0.05 + 0.95 * (1 - t_idx / layers))
    elif weight_type == 'ease out':
        weight = weight * (0.05 + 0.95 * (t_idx / layers))
    elif weight_type == 'ease in-out':
        weight = weight * (0.05 + 0.95 * (1 - abs(t_idx - (layers/2)) / (layers/2)))
    elif weight_type == 'reverse in-out':
        weight = weight * (0.05 + 0.95 * (abs(t_idx - (layers/2)) / (layers/2)))
    elif weight_type == 'weak input' and block_type == 'input':
        weight = weight * 0.2
    elif weight_type == 'weak middle' and block_type == 'middle':
        weight = weight * 0.2
    elif weight_type == 'weak output' and block_type == 'output':
        weight = weight * 0.2
    elif weight_type == 'strong middle' and (block_type == 'input' or block_type == 'output'):
        weight = weight * 0.2
    elif isinstance(weight, dict):
        if t_idx not in weight:
            return 0

        weight = weight[t_idx]

        if cond_alt is not None and t_idx in cond_alt:
            cond = cond_alt[t_idx]
            del cond_alt

    if unfold_batch:
        # Check AnimateDiff context window
        if ad_params is not None and ad_params["sub_idxs"] is not None:
            if isinstance(weight, torch.Tensor):
                weight = tensor_to_size(weight, ad_params["full_length"])
                weight = torch.Tensor(weight[ad_params["sub_idxs"]])
                if torch.all(weight == 0):
                    return 0
                weight = weight.repeat(len(cond_or_uncond), 1, 1) # repeat for cond and uncond
            elif weight == 0:
                return 0

            # if image length matches or exceeds full_length get sub_idx images
            if cond.shape[0] >= ad_params["full_length"]:
                cond = torch.Tensor(cond[ad_params["sub_idxs"]])
                uncond = torch.Tensor(uncond[ad_params["sub_idxs"]])
            # otherwise get sub_idxs images
            else:
                cond = tensor_to_size(cond, ad_params["full_length"])
                uncond = tensor_to_size(uncond, ad_params["full_length"])
                cond = cond[ad_params["sub_idxs"]]
                uncond = uncond[ad_params["sub_idxs"]]
        else:
            if isinstance(weight, torch.Tensor):
                weight = tensor_to_size(weight, batch_prompt)
                if torch.all(weight == 0):
                    return 0
                weight = weight.repeat(len(cond_or_uncond), 1, 1) # repeat for cond and uncond
            elif weight == 0:
                return 0

            cond = tensor_to_size(cond, batch_prompt)
            uncond = tensor_to_size(uncond, batch_prompt)

        k_cond = ipadapter.ip_layers.to_kvs[k_key](cond)
        k_uncond = ipadapter.ip_layers.to_kvs[k_key](uncond)
        v_cond = ipadapter.ip_layers.to_kvs[v_key](cond)
        v_uncond = ipadapter.ip_layers.to_kvs[v_key](uncond)
    else:
        # TODO: should we always convert the weights to a tensor?
        if isinstance(weight, torch.Tensor):
            weight = tensor_to_size(weight, batch_prompt)
            if torch.all(weight == 0):
                return 0
            weight = weight.repeat(len(cond_or_uncond), 1, 1) # repeat for cond and uncond
        elif weight == 0:
            return 0

        k_cond = ipadapter.ip_layers.to_kvs[k_key](cond).repeat(batch_prompt, 1, 1)
        k_uncond = ipadapter.ip_layers.to_kvs[k_key](uncond).repeat(batch_prompt, 1, 1)
        v_cond = ipadapter.ip_layers.to_kvs[v_key](cond).repeat(batch_prompt, 1, 1)
        v_uncond = ipadapter.ip_layers.to_kvs[v_key](uncond).repeat(batch_prompt, 1, 1)

    ip_k = torch.cat([(k_cond, k_uncond)[i] for i in cond_or_uncond], dim=0)
    ip_v = torch.cat([(v_cond, v_uncond)[i] for i in cond_or_uncond], dim=0)
    
    if embeds_scaling == 'K+mean(V) w/ C penalty':
        scaling = float(ip_k.shape[2]) / 1280.0
        weight = weight * scaling
        ip_k = ip_k * weight
        ip_v_mean = torch.mean(ip_v, dim=1, keepdim=True)
        ip_v = (ip_v - ip_v_mean) + ip_v_mean * weight
        out_ip = optimized_attention(q, ip_k, ip_v, extra_options["n_heads"])
        del ip_v_mean
    elif embeds_scaling == 'K+V w/ C penalty':
        scaling = float(ip_k.shape[2]) / 1280.0
        weight = weight * scaling
        ip_k = ip_k * weight
        ip_v = ip_v * weight
        out_ip = optimized_attention(q, ip_k, ip_v, extra_options["n_heads"])
    elif embeds_scaling == 'K+V':
        ip_k = ip_k * weight
        ip_v = ip_v * weight
        out_ip = optimized_attention(q, ip_k, ip_v, extra_options["n_heads"])
    else:
        #ip_v = ip_v * weight
        out_ip = optimized_attention(q, ip_k, ip_v, extra_options["n_heads"])
        out_ip = out_ip * weight # I'm doing this to get the same results as before

    if mask is not None:
        mask_h = oh / math.sqrt(oh * ow / seq_len)
        mask_h = int(mask_h) + int((seq_len % int(mask_h)) != 0)
        mask_w = seq_len // mask_h

        # check if using AnimateDiff and sliding context window
        if (mask.shape[0] > 1 and ad_params is not None and ad_params["sub_idxs"] is not None):
            # if mask length matches or exceeds full_length, get sub_idx masks
            if mask.shape[0] >= ad_params["full_length"]:
                mask = torch.Tensor(mask[ad_params["sub_idxs"]])
                mask = F.interpolate(mask.unsqueeze(1), size=(mask_h, mask_w), mode="bilinear").squeeze(1)
            else:
                mask = F.interpolate(mask.unsqueeze(1), size=(mask_h, mask_w), mode="bilinear").squeeze(1)
                mask = tensor_to_size(mask, ad_params["full_length"])
                mask = mask[ad_params["sub_idxs"]]
        else:
            mask = F.interpolate(mask.unsqueeze(1), size=(mask_h, mask_w), mode="bilinear").squeeze(1)
            mask = tensor_to_size(mask, batch_prompt)

        mask = mask.repeat(len(cond_or_uncond), 1, 1)
        mask = mask.view(mask.shape[0], -1, 1).repeat(1, 1, out.shape[2])

        # covers cases where extreme aspect ratios can cause the mask to have a wrong size
        mask_len = mask_h * mask_w
        if mask_len < seq_len:
            pad_len = seq_len - mask_len
            pad1 = pad_len // 2
            pad2 = pad_len - pad1
            mask = F.pad(mask, (0, 0, pad1, pad2), value=0.0)
        elif mask_len > seq_len:
            crop_start = (mask_len - seq_len) // 2
            mask = mask[:, crop_start:crop_start+seq_len, :]

        out_ip = out_ip * mask

    #out = out + out_ip

    return out_ip.to(dtype=dtype)
