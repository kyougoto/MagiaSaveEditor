"""JSON 序列化：与 JS JSON.stringify 逐字节等价的实现。

客户端保存链路（profiles.js storageJson）依赖 JSON.stringify 的规范化文本：
  - 无多余空白
  - 整数不带小数点
  - 非 ASCII 字符原样输出（不转义）
  - 孤立 UTF-16 代理转义为 \\uXXXX（storageJson 显式处理）
解码/编码 json-shapes-v1 时需要逐字节比对，所以这里不能直接用 json.dumps 默认参数。
"""

import math

_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def utf8_len(text):
    """UTF-8 字节长度（等价 Java String.getBytes(UTF_8).length）。"""
    return len(text.encode("utf-8", "surrogatepass"))


def number_text(value):
    """JS Number::toString 的常见子集。"""
    if isinstance(value, bool):  # bool 是 int 子类，先拦截
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "null"
        if value == int(value) and abs(value) < 1e21:
            return str(int(value))
        text = repr(value)
        if "e" in text:
            mantissa, exp = text.split("e")
            sign = "+" if int(exp) >= 0 else "-"
            text = mantissa + "e" + sign + str(abs(int(exp)))
        return text
    raise TypeError("not a number: %r" % (value,))


def quote(text):
    """JS JSON.stringify 的字符串转义：控制字符转义，非 ASCII 原样，孤立代理转义。"""
    out = ['"']
    for ch in text:
        code = ord(ch)
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif code < 0x20:
            out.append("\\u%04x" % code)
        elif 0xD800 <= code <= 0xDFFF:
            # Python 字符串里的孤立代理：JS 侧 storageJson 把它写成 \\uXXXX。
            out.append("\\u%04x" % code)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def dumps(value):
    """等价 JSON.stringify(value)。"""
    parts = []
    _write(value, parts)
    return "".join(parts)


def _write(value, parts):
    if value is None:
        parts.append("null")
    elif isinstance(value, bool):
        parts.append("true" if value else "false")
    elif isinstance(value, (int, float)):
        parts.append(number_text(value))
    elif isinstance(value, str):
        parts.append(quote(value))
    elif isinstance(value, (list, tuple)):
        parts.append("[")
        for i, item in enumerate(value):
            if i:
                parts.append(",")
            _write(item, parts)
        parts.append("]")
    elif isinstance(value, dict):
        parts.append("{")
        first = True
        for key, item in value.items():
            if not first:
                parts.append(",")
            first = False
            parts.append(quote(str(key)))
            parts.append(":")
            _write(item, parts)
        parts.append("}")
    else:
        raise TypeError("unsupported type: %r" % (type(value),))
