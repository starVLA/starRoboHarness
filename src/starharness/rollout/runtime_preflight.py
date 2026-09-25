"""Probe the controller's actual imports and wire codec before remote startup."""

import importlib
import json
import sys


def check():
    names = (
        "websockets.sync.client", "cv2", "PIL.Image", "msgpack", "numpy",
        "imageio", "imageio_ffmpeg", "scipy",
        "deployment.model_server.tools.msgpack_numpy",
        "starharness.rollout.persistent_episode",
        "hybrid_rollout.robodojo.robodojo_server.protocol",
    )
    modules = {name: importlib.import_module(name) for name in names}
    np = modules["numpy"]
    codec = modules["deployment.model_server.tools.msgpack_numpy"]
    actions = np.arange(700, dtype=np.float32).reshape(50, 14)
    decoded = codec.unpackb(codec.Packer().pack({"actions": actions}))
    np.testing.assert_array_equal(decoded["actions"], actions)
    return {
        "executable": sys.executable, "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "imports": {name: module.__file__ for name, module in modules.items()},
        "codec_roundtrip": "passed",
    }


if __name__ == "__main__":
    print(json.dumps(check()))
