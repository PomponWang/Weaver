import random
from collections.abc import Mapping, Sequence
import numpy as np
import torch
from torch.utils.data.dataloader import default_collate


def collate_fn(batch):
    """
    collate function for point cloud which support dict and list,
    'coord' is necessary to determine 'offset'
    """
    if not isinstance(batch, Sequence):
        raise TypeError(f"{batch.dtype} is not supported.")

    if isinstance(batch[0], torch.Tensor):
        return torch.cat(list(batch))
    elif isinstance(batch[0], str):
        # str is also a kind of Sequence, judgement should before Sequence
        return list(batch)
    elif isinstance(batch[0], Sequence):
        for data in batch:
            data.append(torch.tensor([data[0].shape[0]]))
        batch = [collate_fn(samples) for samples in zip(*batch)]
        batch[-1] = torch.cumsum(batch[-1], dim=0).int()
        return batch
    elif isinstance(batch[0], Mapping):
        batch = {key: collate_fn([d[key] for d in batch]) for key in batch[0]}
        for key in batch.keys():
            if "offset" in key:
                batch[key] = torch.cumsum(batch[key], dim=0)
        return batch
    else:
        return default_collate(batch)


def point_collate_fn(batch, mix_prob=0, dynamic_batching=False, max_points_per_batch=1e7):
    if dynamic_batching:
        assert len(batch[0]) == 2, "batch[0]=[data_dict, num_points]"
        batch = sorted(batch, key=lambda x:x[1], reverse=True)
        data_dicts, point_counts = zip(*batch)
        current_batch = []
        current_points = 0
        sub_batches = []
        for data, num_points in zip(data_dicts, point_counts):
            if current_points + num_points > max_points_per_batch:
                current_batch = point_collate_fn(current_batch)
                sub_batches.append(current_batch)
                current_batch = []
                current_points = 0
            current_batch.append(data)
            current_points += num_points
        if current_batch:
            current_batch = point_collate_fn(current_batch)
            sub_batches.append(current_batch)
        return sub_batches
    else:
        assert isinstance(batch[0], Mapping)  # currently, only support input_dict, rather than input_list
        batch = collate_fn(batch)
        if "offset" in batch.keys():
            # Mix3d (https://arxiv.org/pdf/2110.02210.pdf)
            if random.random() < mix_prob:
                batch["offset"] = torch.cat([batch["offset"][1:-1:2], batch["offset"][-1].unsqueeze(0)], dim=0)
        return batch

def gaussian_kernel(dist2: np.array, a: float = 1, c: float = 5):
    """
    Args:
        a: scale factor
        c: sigma/variance
    """
    return a * np.exp(-dist2 / (2 * c**2))