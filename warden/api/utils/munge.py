import ctypes
import ctypes.util

# Load library
libname = ctypes.util.find_library("munge")
if not libname:
    raise RuntimeError("libmunge not found")

lib = ctypes.CDLL(libname)

munge_ctx_t = ctypes.c_void_p
uid_t = ctypes.c_uint
gid_t = ctypes.c_uint


lib.munge_ctx_create.argtypes = []
lib.munge_ctx_create.restype = munge_ctx_t

lib.munge_ctx_destroy.argtypes = [munge_ctx_t]
lib.munge_ctx_destroy.restype = None

lib.munge_decode.argtypes = [
    ctypes.c_char_p,  # cred
    munge_ctx_t,  # ctx
    ctypes.POINTER(ctypes.c_void_p),  # buf
    ctypes.POINTER(ctypes.c_int),  # len
    ctypes.POINTER(uid_t),  # uid
    ctypes.POINTER(gid_t),  # gid
]
lib.munge_decode.restype = ctypes.c_int

lib.munge_strerror.argtypes = [ctypes.c_int]
lib.munge_strerror.restype = ctypes.c_char_p


class MungeError(Exception):
    pass


class MungeReplayError(MungeError):
    pass


class MungeExpiredError(MungeError):
    pass


def decode_munge(token: bytes) -> tuple[bytes, int]:
    """Decode a munge token."""
    ctx = lib.munge_ctx_create()
    if not ctx:
        raise RuntimeError("munge_ctx_create failed")

    buf = ctypes.c_void_p()
    length = ctypes.c_int()
    uid = uid_t()
    gid = gid_t()

    try:
        rc = lib.munge_decode(
            token,
            ctx,
            ctypes.byref(buf),
            ctypes.byref(length),
            ctypes.byref(uid),
            ctypes.byref(gid),
        )

        if rc != 0:
            msg = lib.munge_strerror(rc).decode()
            if "expired" in msg.lower():
                raise MungeExpiredError(msg)
            # We ignore replay errors for now
            if not "replay" in msg.lower():
                msg = lib.munge_strerror(rc)
                raise MungeError(msg.decode() if msg else f"munge error {rc}")

        payload = ctypes.string_at(buf.value, length.value)
        return payload, uid.value

    finally:
        lib.munge_ctx_destroy(ctx)
