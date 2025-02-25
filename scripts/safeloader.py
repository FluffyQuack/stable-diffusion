# Source: https://github.com/AUTOMATIC1111/stable-diffusion-webui/blob/master/modules/safe.py
import io
import pickle
import collections
import sys
import traceback

import torch
import numpy
import _codecs
import zipfile
import re


# PyTorch 1.13 and later have _TypedStorage renamed to TypedStorage
TypedStorage = torch.storage.TypedStorage \
    if hasattr(torch.storage, 'TypedStorage') \
    else torch.storage._TypedStorage


def encode(*args):
    out = _codecs.encode(*args)
    return out


class RestrictedUnpickler(pickle.Unpickler):
    def persistent_load(self, saved_id):
        assert saved_id[0] == 'storage'
        return TypedStorage()

    def find_class(self, module, name):
        if module == 'collections' and name == 'OrderedDict':
            return getattr(collections, name)
        if module == 'torch._utils' and name in ['_rebuild_tensor_v2',
                                                 '_rebuild_parameter',
                                                 '_rebuild_tensor']:
            return getattr(torch._utils, name)
        if module == 'torch' and name in ['FloatStorage',
                                          'HalfStorage',
                                          'IntStorage',
                                          'LongStorage',
                                          'DoubleStorage']:
            return getattr(torch, name)
        if module == 'torch.nn.modules.container' and name in ['ParameterDict']:
            return getattr(torch.nn.modules.container, name)
        if module == 'numpy.core.multiarray' and name == 'scalar':
            return numpy.core.multiarray.scalar
        if module == 'numpy' and name == 'dtype':
            return numpy.dtype
        if module == '_codecs' and name == 'encode':
            return encode
        if module == "pytorch_lightning.callbacks" and\
           name == 'model_checkpoint':
            import pytorch_lightning.callbacks
            return pytorch_lightning.callbacks.model_checkpoint
        if module == "pytorch_lightning.callbacks.model_checkpoint" and\
           name == 'ModelCheckpoint':
            import pytorch_lightning.callbacks.model_checkpoint
            return pytorch_lightning.callbacks.model_checkpoint.ModelCheckpoint
        if module == "__builtin__" and name == 'set':
            return set

        # Forbid everything else.
        raise pickle.UnpicklingError(f"global '{module}/{name}' is forbidden")


allowed_zip_names = ["archive/data.pkl", "archive/version"]
allowed_zip_names_re = re.compile(r"^archive/data/\d+$")


def check_zip_filenames(filename, names):
    for name in names:
        if name in allowed_zip_names:
            continue
        if allowed_zip_names_re.match(name):
            continue
        raise Exception(f"bad file inside {filename}: {name}")


def check_pt(filename):
    try:
        # new pytorch format is a zip file
        with zipfile.ZipFile(filename) as z:
            check_zip_filenames(filename, z.namelist())
            with z.open('archive/data.pkl') as file:
                unpickler = RestrictedUnpickler(file)
                unpickler.load()
    except zipfile.BadZipfile:
        # if it's not a zip file, it's an olf pytorch format, with five objects written to pickle
        with open(filename, "rb") as file:
            unpickler = RestrictedUnpickler(file)
            for i in range(5):
                unpickler.load()


def load(filename, *args, **kwargs):
    try:
        check_pt(filename)
    except pickle.UnpicklingError:
        print(f"Error verifying pickled file from {filename}:",
              file=sys.stderr)
        print(traceback.format_exc(),
              file=sys.stderr)
        print(f"-----> !!!! The file is most likely corrupted !!!! <-----",
              file=sys.stderr)
        return None
    except Exception:
        print(f"Error verifying pickled file from {filename}:",
              file=sys.stderr)
        print(traceback.format_exc(),
              file=sys.stderr)
        print(f"\nThe file may be malicious, so the program is not going "
              "to read it.",
              file=sys.stderr)
        return None
    return unsafe_torch_load(filename, *args, **kwargs)


unsafe_torch_load = torch.load
torch.load = load
