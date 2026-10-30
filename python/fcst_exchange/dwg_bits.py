# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded DWG bit primitives, independent of native/vendor execution.

Bits within a byte are consumed most significant first. Raw numeric bytes are
little endian; handle payload bytes are big endian. Readers never cross their
declared stream boundary, including for separate modern text streams.
"""
from dataclasses import dataclass
import math
import struct
from .core import reject


@dataclass
class Bits:
    data:bytes
    position:int=0
    end:int|None=None

    def __post_init__(self):
        if self.end is None:self.end=len(self.data)*8
        if (not isinstance(self.data,bytes) or type(self.position) is not int or type(self.end) is not int
                or not 0<=self.position<=self.end<=len(self.data)*8):reject('td_bits_bounds')

    def take(self,count):
        if type(count) is not int or not 0<=count<=64 or self.position+count>self.end:reject('td_bits_truncated')
        result=0
        while count:
            byte,bit=divmod(self.position,8);step=min(count,8-bit)
            result=(result<<step)|((self.data[byte]>>(8-bit-step))&((1<<step)-1))
            self.position+=step;count-=step
        return result

    def raw(self,count):
        if type(count) is not int or not 0<=count<=1048576 or self.position+8*count>self.end:reject('td_bits_size')
        return bytes(self.take(8) for _ in range(count))

    def bl(self):
        tag=self.take(2)
        if tag==3:reject('td_bits_long_tag')
        return struct.unpack('<i',self.raw(4))[0] if tag==0 else self.take(8) if tag==1 else 0

    def bs(self):
        tag=self.take(2)
        return int.from_bytes(self.raw(2),'little') if tag==0 else self.take(8) if tag==1 else 0 if tag==2 else 256

    def bd(self):
        tag=self.take(2)
        if tag==3:reject('td_bits_double_tag')
        value=struct.unpack('<d',self.raw(8))[0] if tag==0 else 1.0 if tag==1 else 0.0
        if not math.isfinite(value):reject('td_bits_nonfinite')
        return value

    def point(self):return tuple(self.bd() for _ in range(3))

    def text(self):
        length=self.bs()
        if length>32768:reject('td_bits_text_limit')
        try:value=self.raw(length*2).decode('utf-16-le')
        except UnicodeError:reject('td_bits_text_encoding')
        if '\0' in value:reject('td_bits_text_nul')
        return value

    def handle(self,owner):
        code=self.take(4);length=self.take(4)
        if length>8:reject('td_bits_handle_size')
        value=int.from_bytes(self.raw(length),'big')
        if code in {0,2,3,4,5}:target=value
        elif code in {6,8}:
            if length:reject('td_bits_handle_relative')
            target=owner+(1 if code==6 else -1)
        elif code in {10,12}:target=owner+(value if code==10 else -value)
        else:reject('td_bits_handle_code')
        if not 0<=target<=18446744073709551615:reject('td_bits_handle_range')
        return {'code':code,'value':value,'target':target}


def fixed_double(value,width):
    """Retain full-width encodings; expand compressed zero/one by 64 bits."""
    if type(value) not in (int,float) or not math.isfinite(value):reject('td_edit_number')
    if width==2:
        if value in (0,1):return (2 if value==0 else 1),2
        return int.from_bytes(struct.pack('<d',value),'big'),66
    if width!=66:reject('td_edit_encoding_width')
    return int.from_bytes(struct.pack('<d',value),'big'),66


def replace_bits(raw,start,width,value):
    if (not isinstance(raw,bytes) or type(start) is not int or type(width) is not int
            or not 0<=start<=start+width<=len(raw)*8 or width>66
            or type(value) is not int or not 0<=value<(1<<width)):reject('td_edit_bit_range')
    out=bytearray(raw)
    for i in range(width):
        byte,bit=divmod(start+i,8);mask=1<<(7-bit)
        out[byte]=(out[byte]&~mask)|(((value>>(width-i-1))&1)<<(7-bit))
    return bytes(out)


def scalar_record(row,spans,changes):
    """Splice only declared BD spans; preserve all following stream bits."""
    raw=bytes.fromhex(row['data']);count=row['bits'];original=count
    if not 0<count<=134217728 or len(raw)!=(count+7)//8:reject('td_edit_bit_range')
    value=int.from_bytes(raw,'big')>>(len(raw)*8-count)
    occupied=[]
    for name in sorted(changes,key=lambda k:spans[k][0],reverse=True):
        start,width=spans[name];encoded,size=fixed_double(changes[name],width)
        if not 0<=start<start+width<=original or any(start<b and a<start+width for a,b in occupied):reject('td_edit_bit_range')
        occupied.append((start,start+width));tail=count-start-width
        value=((value>>(tail+width))<<(tail+size))|(encoded<<tail)|(value&((1<<tail)-1))
        count+=size-width
    raw=(value<<(-count%8)).to_bytes((count+7)//8,'big');delta=count-original
    return {**row,'data':raw.hex(),'bits':count,'object_bits':row['object_bits']+delta,'data_bits':row['data_bits']+delta}
