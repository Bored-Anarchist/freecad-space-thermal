# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned bounded readers for the declared modern TD object payload profile.

The object data, text and handle streams are separate. A field reader cannot
consume another stream or treat source expressions as executable Python/Fortran.
Numeric selector fields without established semantic mappings remain explicit.
"""
from dataclasses import dataclass
from .core import reject
from .dwg_bits import Bits


@dataclass
class Filer:
    row:dict

    def __post_init__(self):
        row=self.row
        try:
            if not isinstance(row['data'],str) or len(row['data'])>33554432:reject('td_filer_metadata')
            raw=bytes.fromhex(row['data']);size=row['bits'];end=row['data_bits']-(row['object_bits']-size)
            valid=(all(type(row[k]) is int and row[k]>=0 for k in ('bits','data_bits','object_bits','string_bits','handle_bits'))
                   and row['object_bits']>=size and 1<=end<=size and size<=len(raw)*8
                   and len(raw)==(size+7)//8 and row['object_bits']-row['data_bits']==row['handle_bits'])
        except (KeyError,ValueError,TypeError):reject('td_filer_metadata')
        if not valid:reject('td_filer_metadata')
        flag=Bits(raw,end-1,end).take(1);header=1;length=0
        if flag:
            if end<17:reject('td_filer_string_header')
            length=int.from_bytes(Bits(raw,end-17,end-1).raw(2),'little');header=17
            if length&32768:
                if end<33:reject('td_filer_string_header')
                high=int.from_bytes(Bits(raw,end-33,end-17).raw(2),'little')
                length=(length&32767)|(high<<15);header=33
        if length!=row['string_bits'] or length>end-header:reject('td_filer_string_size')
        start=end-header-length
        self.data=Bits(raw,0,start);self.strings=Bits(raw,start,start+length)
        self.handles=Bits(raw,end,size);self.raw=raw;self.spans={};self.values=0

    def count(self):
        value=self.data.bl()
        if not 0<=value<=10000 or self.values+value>100000:reject('td_filer_array_limit')
        self.values+=value;return value

    def version(self,expected):
        value=self.data.bl()
        if value!=expected:reject('td_filer_version')
        return value

    def number(self,name):
        if name in self.spans:reject('td_filer_duplicate_field')
        start=self.data.position;value=self.data.bd()
        self.spans[name]=(start,self.data.position-start);return value

    def text(self):
        marker=self.data.bl()
        if marker<0:
            value=self.strings.text()
            if len(value.encode('utf-16-le'))//2!=-marker:reject('td_filer_text_length')
        else:
            if marker>32768:reject('td_filer_text_limit')
            try:value=self.data.raw(marker).decode('ascii')
            except UnicodeError:reject('td_filer_legacy_text_encoding')
            if '\0' in value:reject('td_filer_text_nul')
        self.values+=len(value)
        if self.values>100000:reject('td_filer_value_limit')
        return value

    def integers(self):return tuple(self.data.bl() for _ in range(self.count()))
    def doubles(self):return tuple(self.data.bd() for _ in range(self.count()))
    def flags(self):return tuple(self.data.take(1) for _ in range(self.count()))
    def texts(self):return tuple(self.text() for _ in range(self.count()))

    def table_metadata(self):
        self.version(1)
        return {'column_a':self.integers(),'column_b':self.integers(),'enabled':self.flags()}

    def expression(self):
        self.version(5)
        return {'selectors':tuple(self.data.bl() for _ in range(3)),
                'text':self.text(),'alternate':self.text(),'table':self.table_metadata(),
                'mode':self.data.bl(),'dimension':self.data.bl(),'dimensional':bool(self.data.take(1)),
                'dimension_table':self.table_metadata()}

    def multi_expression(self):
        self.version(3)
        return {'texts':self.texts(),'selector':self.data.bl(),
                'options':(self.data.bl(),self.data.bl()),'text':self.text(),
                'table':self.table_metadata(),'mode':self.data.bl(),'dimension':self.data.bl()}

    def logic(self):
        self.version(5)
        result={'comment':self.text(),'identifier':self.data.bl(),'namespace':self.text(),
                'condition':self.text(),'mode':self.data.bl(),'expression':self.expression(),'extra':self.text()}
        self.version(3);result['statements']=self.texts()
        self.version(1)
        result['options']=tuple(self.data.bl() for _ in range(4));result['enabled']=self.flags()
        result['priorities']=self.integers();result['option_text']=self.text()
        return result

    def connections(self):
        self.version(2);result=[]
        for _ in range(self.count()):
            kind=self.data.bl()
            if kind not in {1,2}:reject('td_filer_connection_kind')
            self.version(1)
            if kind==1:
                result.append({'kind':'entity-node','reference':self.handle(),'index':self.data.bl()})
            else:result.append({'kind':'named-selection','name':self.text()})
        # In a normal file filer, v2 omits the transient resolved-node cache.
        # It is not a persistent source dependency or an extra data field.
        return tuple(result)

    def handle(self):return self.handles.handle(self.row['handle'])

    def finish(self):
        if self.data.position!=self.data.end or self.strings.position!=self.strings.end:reject('td_filer_unconsumed_stream')
        padding=self.handles.end-self.handles.position
        if padding>7:reject('td_filer_unconsumed_handles')
        # Object alignment bits are not necessarily zero in acquired drawings.
        # Keep them byte-exact in the retained payload; they grant no semantics.
        return padding,self.handles.take(padding)


def expression_is_constant(value):
    return (not value['text'] and not value['alternate'] and value['selectors']==(-1,0,0)
            and value['mode']==0
            and all(not x for table in (value['table'],value['dimension_table']) for x in table.values()))


def logic_is_empty(value):
    return (not value['condition'] and not value['extra'] and not value['statements']
            and not value['option_text'] and value['identifier']==-1 and value['mode']==1
            and expression_is_constant(value['expression']) and not any(value['options'])
            and not any(value['enabled']) and not any(value['priorities']))
