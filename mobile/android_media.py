"""Плашка плеера в шторке Android: Python → Java MediaBridge через JNI.

В PySide для Android нет QJniObject, поэтому JNI вызывается через ctypes:
JavaVM и Context отдаёт сам Qt (QtAndroidPrivate::javaVM/context из
libQt6Core). Класс приложения грузится через ClassLoader контекста —
FindClass из потока Qt видит только системные классы.

Все вызовы — из главного потока Qt (слоты и QTimer): JNIEnv привязан к
потоку. Ссылки, созданные здесь, удаляются сразу: Python не возвращается
в Java, и локальные ссылки иначе копились бы до конца работы.
"""

from __future__ import annotations

import ctypes
import logging
import platform
import sys

log = logging.getLogger(__name__)

NONE, PLAY, PAUSE, NEXT, PREV, SEEK_BASE = -1, 1, 2, 3, 4, 10

# Номера функций в таблицах JNI (jni.h из NDK r28c, без комментариев).
_ATTACH_CURRENT_THREAD = 4
_FIND_CLASS = 6
_EXCEPTION_DESCRIBE = 16
_EXCEPTION_CLEAR = 17
_NEW_GLOBAL_REF = 21
_DELETE_LOCAL_REF = 23
_GET_OBJECT_CLASS = 31
_GET_METHOD_ID = 33
_CALL_OBJECT_METHOD_A = 36
_GET_STATIC_METHOD_ID = 113
_CALL_STATIC_LONG_METHOD_A = 134
_CALL_STATIC_VOID_METHOD_A = 143
_NEW_STRING = 163
_EXCEPTION_CHECK = 228

_P = ctypes.c_void_p
_BRIDGE = "org.quantis.mobile.MediaBridge"


def is_android() -> bool:
    return hasattr(sys, "getandroidapilevel")


class _Jni:
    def __init__(self, env: int | None = None, context: int | None = None) -> None:
        if env is not None:  # проверка на компьютере: своя JVM и свой «контекст»
            self.env, self.context = env, context
            return
        abi = {"aarch64": "arm64-v8a", "x86_64": "x86_64"}[platform.machine()]
        qtcore = ctypes.CDLL(f"libQt6Core_{abi}.so")
        java_vm = qtcore._ZN16QtAndroidPrivate6javaVMEv
        java_vm.restype = _P
        context = qtcore._ZN16QtAndroidPrivate7contextEv
        context.restype = _P
        vm = java_vm()
        if not vm:
            raise RuntimeError("Qt не отдал JavaVM")
        attach = self._fn(vm, _ATTACH_CURRENT_THREAD, ctypes.c_int, _P, _P, _P)
        env = _P()
        if attach(vm, ctypes.byref(env), None) != 0:
            raise RuntimeError("AttachCurrentThread не удался")
        self.env = env.value
        self.context = context()
        if not self.context:
            raise RuntimeError("Qt не отдал Context")

    @staticmethod
    def _fn(obj: int, index: int, restype, *argtypes):
        table = ctypes.cast(ctypes.cast(obj, ctypes.POINTER(_P))[0], ctypes.POINTER(_P))
        return ctypes.CFUNCTYPE(restype, *argtypes)(table[index])

    def call(self, index: int, restype, *args, argtypes=()):
        types = argtypes or tuple(_P for _ in args)
        # Массивы (jvalue[], jchar[]) — явным указателем; сами массивы живы,
        # пока на них ссылается args.
        passed = [
            ctypes.cast(a, _P) if isinstance(a, ctypes.Array) else a for a in args
        ]
        result = self._fn(self.env, index, restype, _P, *types)(self.env, *passed)
        self.check()
        return result

    def check(self) -> None:
        raised = self._fn(self.env, _EXCEPTION_CHECK, ctypes.c_ubyte, _P)(self.env)
        if raised:
            self._fn(self.env, _EXCEPTION_DESCRIBE, None, _P)(self.env)  # в logcat
            self._fn(self.env, _EXCEPTION_CLEAR, None, _P)(self.env)
            raise RuntimeError("исключение Java (см. logcat)")

    def delete(self, ref: int | None) -> None:
        if ref:
            self._fn(self.env, _DELETE_LOCAL_REF, None, _P, _P)(self.env, ref)

    def string(self, text: str) -> int:
        data = text.encode("utf-16-le")
        chars = (ctypes.c_uint16 * (len(data) // 2)).from_buffer_copy(data)
        return self.call(
            _NEW_STRING, _P, chars, len(chars), argtypes=(_P, ctypes.c_int32)
        )

    def method_id(self, cls: int, name: str, sig: str, *, static: bool) -> int:
        index = _GET_STATIC_METHOD_ID if static else _GET_METHOD_ID
        mid = self.call(
            index,
            _P,
            cls,
            name.encode(),
            sig.encode(),
            argtypes=(_P, ctypes.c_char_p, ctypes.c_char_p),
        )
        if not mid:
            raise RuntimeError(f"нет метода {name}{sig}")
        return mid

    @staticmethod
    def jvalues(*values: int) -> ctypes.Array:
        return (ctypes.c_uint64 * max(1, len(values)))(
            *[v & 0xFFFFFFFFFFFFFFFF for v in values]
        )

    def load_class(self, name: str) -> int:
        """Класс приложения — через ClassLoader контекста, глобальной ссылкой."""
        ctx_cls = self.call(_GET_OBJECT_CLASS, _P, self.context)
        get_loader = self.method_id(
            ctx_cls, "getClassLoader", "()Ljava/lang/ClassLoader;", static=False
        )
        self.delete(ctx_cls)
        loader = self.call(
            _CALL_OBJECT_METHOD_A, _P, self.context, get_loader, self.jvalues()
        )
        loader_cls = self.call(_GET_OBJECT_CLASS, _P, loader)
        load = self.method_id(
            loader_cls,
            "loadClass",
            "(Ljava/lang/String;)Ljava/lang/Class;",
            static=False,
        )
        self.delete(loader_cls)
        jname = self.string(name)
        try:
            cls = self.call(
                _CALL_OBJECT_METHOD_A, _P, loader, load, self.jvalues(jname)
            )
        finally:
            self.delete(jname)
            self.delete(loader)
        global_cls = self.call(_NEW_GLOBAL_REF, _P, cls)
        self.delete(cls)
        return global_cls


class MediaControls:
    """Плашка в шторке. Вне Android и при любой ошибке JNI — ничего не делает."""

    def __init__(self) -> None:
        self._jni: _Jni | None = None
        if not is_android():
            return
        try:
            jni = _Jni()
            cls = jni.load_class(_BRIDGE)
            self._cls = cls
            self._init = jni.method_id(
                cls, "init", "(Landroid/content/Context;)V", static=True
            )
            self._update = jni.method_id(
                cls, "update", "(Ljava/lang/String;Ljava/lang/String;ZJJ)V", static=True
            )
            self._poll = jni.method_id(cls, "poll", "()J", static=True)
            self._release = jni.method_id(cls, "release", "()V", static=True)
            jni.call(
                _CALL_STATIC_VOID_METHOD_A,
                None,
                cls,
                self._init,
                jni.jvalues(jni.context),
            )
            self._jni = jni
        except Exception:
            log.exception("Плашка плеера недоступна")

    def update(
        self, title: str, artist: str, playing: bool, position_ms: int, duration_ms: int
    ) -> None:
        jni = self._jni
        if jni is None:
            return
        try:
            jtitle, jartist = jni.string(title), jni.string(artist)
            try:
                jni.call(
                    _CALL_STATIC_VOID_METHOD_A,
                    None,
                    self._cls,
                    self._update,
                    jni.jvalues(
                        jtitle, jartist, int(playing), position_ms, duration_ms
                    ),
                )
            finally:
                jni.delete(jtitle)
                jni.delete(jartist)
        except Exception:
            log.exception("Не удалось обновить плашку")

    def poll(self) -> int:
        jni = self._jni
        if jni is None:
            return NONE
        try:
            return int(
                jni.call(
                    _CALL_STATIC_LONG_METHOD_A,
                    ctypes.c_int64,
                    self._cls,
                    self._poll,
                    jni.jvalues(),
                )
            )
        except Exception:
            log.exception("Не удалось прочитать команды плашки")
            return NONE

    def release(self) -> None:
        jni = self._jni
        if jni is None:
            return
        try:
            jni.call(
                _CALL_STATIC_VOID_METHOD_A,
                None,
                self._cls,
                self._release,
                jni.jvalues(),
            )
        except Exception:
            log.exception("Не удалось убрать плашку")
