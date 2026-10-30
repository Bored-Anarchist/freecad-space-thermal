// SPDX-License-Identifier: GPL-3.0-or-later
// Owned standalone converter. Its linked LibreDWG backend is GPL-3.0-or-later.
// This program is not linked into the FCST engine or its Python modules.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
extern "C" {
#include <dwg.h>
#include <dwg_api.h>
#include <out_json.h>
#include <bits.h>
#include <encode.h>
}
#undef restrict

#ifndef FCST_PATCH_SHA256
#define FCST_PATCH_SHA256 "unset"
#endif

namespace {
const char* stage="operation";
constexpr const char* protocol = "fcst-dwg-native/2";
constexpr std::size_t max_bytes = 67108864;
constexpr std::size_t max_payload = 16777216;
struct Document {
    Dwg_Data data{};
    ~Document() { dwg_free(&data); }
};
void require(bool condition) { if (!condition) throw std::runtime_error("bridge_contract"); }
void quoted(std::ostream& out, const char* text) {
    out << '"';
    if (text) {
        const auto length = strnlen(text, 65537);
        require(length <= 65536);
        for (std::size_t i=0; i<length; ++i) {
            const auto c = static_cast<unsigned char>(text[i]);
            if (c == '"' || c == '\\') out << '\\' << c;
            else if (c < 32) {
                char buffer[7]; std::snprintf(buffer,sizeof(buffer),"\\u%04x",unsigned(c)); out << buffer;
            } else out << c;
        }
    }
    out << '"';
}
void hex(std::ostream& out, const unsigned char* bytes, std::size_t count) {
    require(count <= max_payload && (!count || bytes));
    static constexpr char digits[] = "0123456789abcdef";
    out << '"';
    for (std::size_t i=0; i<count; ++i) out << digits[bytes[i]>>4] << digits[bytes[i]&15];
    out << '"';
}
void opaque(std::ostream& out, const unsigned char* bytes, std::size_t bits) {
    const auto count=(bits+7)/8;require(count<=max_payload && (!count || bytes));
    if (!bits || !(bits%8)) {hex(out,bytes,count);return;}
    std::vector<unsigned char> wire(bytes,bytes+count);unsigned char tail=0;
    // LibreDWG bit_read_bits packs only the final partial byte LSB first.
    // The wire protocol uses ordinary MSB-first bytes throughout.
    for (unsigned i=0;i<bits%8;++i) tail|=((wire.back()>>i)&1)<<(7-i);
    wire.back()=tail;hex(out,wire.data(),wire.size());
}
void class_text(std::ostream& out, const char* value) {
    // Modern class app/cpp names are stored as UCS-2 despite their char* API
    // type. DXF names have a separate upstream UTF-8 conversion.
    if (!value) { quoted(out,nullptr); return; }
    char* utf8=bit_convert_TU(reinterpret_cast<BITCODE_TU>(const_cast<char*>(value)));
    require(utf8); quoted(out,utf8); std::free(utf8);
}
std::vector<unsigned char> wire_bytes(const unsigned char* source,std::size_t bits) {
    require(bits && (bits+7)/8<=max_payload && source);
    std::vector<unsigned char> result(source,source+(bits+7)/8);
    if (bits%8) {
        unsigned char tail=0;
        for (unsigned i=0;i<bits%8;++i) tail|=((result.back()>>i)&1)<<(7-i);
        result.back()=tail;
    }
    return result;
}
struct EditInput {
    std::vector<unsigned char> bytes;std::size_t cursor=0;
    EditInput(const char* file="edits.bin",const char* magic="FCSTEDIT2") {
        require(std::filesystem::is_regular_file(file));
        const auto size=std::filesystem::file_size(file);require(size>=13 && size<=2*max_payload+1048576);
        bytes.resize(size);std::ifstream input(file,std::ios::binary);
        input.read(reinterpret_cast<char*>(bytes.data()),size);require(bool(input));
        cursor=std::strlen(magic);require(std::memcmp(bytes.data(),magic,cursor)==0);
    }
    std::uint64_t number(unsigned count) {
        require(count<=8 && cursor+count<=bytes.size());std::uint64_t value=0;
        for (unsigned i=0;i<count;++i) value|=std::uint64_t(bytes[cursor++])<<(8*i);
        return value;
    }
    std::vector<unsigned char> payload(std::size_t bits) {
        require(bits && bits<=8*max_payload);const auto count=(bits+7)/8;
        require(cursor+count<=bytes.size());std::vector<unsigned char> value(bytes.begin()+cursor,bytes.begin()+cursor+count);cursor+=count;
        if (bits%8) require((value.back()&((1<<(8-bits%8))-1))==0);
        return value;
    }
};
void fresh(const char* name);
struct Chain {
    Bit_Chain value{};
    Chain() {bit_chain_init(&value,4096);value.version=R_2018;value.from_version=R_2018;}
    ~Chain() {bit_chain_free(&value);}
};
void append(Bit_Chain& target,const std::vector<unsigned char>& bytes,std::size_t bits) {
    require((bits+7)/8==bytes.size());
    for (std::size_t i=0;i<bits;++i) bit_write_B(&target,(bytes[i/8]>>(7-i%8))&1);
}
struct NewObject {
    unsigned kind;std::size_t main_bits,text_bits;std::vector<unsigned char> main,text;std::vector<unsigned> references;
};
void create_network() {
    stage="new-network-request";
    fresh("derived.dwg");EditInput input("network.bin","FCSTNEW2");const auto count=input.number(4);require(count && count<=10000);
    std::vector<NewObject> records;std::size_t total=0;
    for (std::size_t i=0;i<count;++i) {
        NewObject record{};record.kind=input.number(1);record.main_bits=input.number(4);record.text_bits=input.number(4);const auto refs=input.number(4);
        require(record.kind>=1 && record.kind<=5 && refs<=10000 && record.text_bits<0x8000);
        record.main=input.payload(record.main_bits);if(record.text_bits) record.text=input.payload(record.text_bits);
        total+=record.main.size()+record.text.size()+refs*4;require(total<=max_payload);
        for (std::size_t j=0;j<refs;++j) {const auto ref=input.number(4);require(ref<=count);record.references.push_back(ref);}
        records.push_back(std::move(record));
    }
    require(input.cursor==input.bytes.size());stage="new-network-document";Document doc;doc.data.header.version=R_2018;doc.data.header.from_version=R_2018;
    require(dwg_add_Document(&doc.data,0)==0);
    stage="new-network-classes";const char* dxf[]={"RCNODE","RCCONDUCTOR","RCHEATLOAD","RCRECTANGLE","RCTD_FDBRICK"};const char* cpp[]={"RcNode","RcConductor","RcHeatLoad","RcRectangle","RcFdBrick"};unsigned classes[5];
    for (unsigned i=0;i<5;++i) {const int id=dwg_add_class(&doc.data,dxf[i],cpp[i],"FCST independent exchange",true);require(id>=500);classes[i]=id;doc.data.dwg_class[id-500].dwg_version=21;}
    auto* space=dwg_model_space_object(&doc.data);require(space && space->tio.object && space->tio.object->tio.BLOCK_HEADER);
    auto* block=space->tio.object->tio.BLOCK_HEADER;std::vector<unsigned> indexes;
    stage="new-network-objects";for (const auto& record:records) {
        const dwg_point_3d a{0,0,0},b{1,0,0};auto* line=dwg_add_LINE(block,&a,&b);require(line && line->parent);
        const auto index=line->parent->objid;auto& object=doc.data.object[index];auto* entity=line->parent;
        auto* unknown=static_cast<Dwg_Entity_UNKNOWN_ENT*>(std::calloc(1,sizeof(Dwg_Entity_UNKNOWN_ENT)));require(unknown);unknown->parent=entity;
        std::free(line);entity->tio.UNKNOWN_ENT=unknown;object.fixedtype=DWG_TYPE_UNKNOWN_ENT;object.type=classes[record.kind-1];
        if (doc.data.opts&DWG_OPTS_INJSON) std::free(object.name);
        if (doc.data.opts&DWG_OPTS_IN) std::free(object.dxfname);
        object.name=(doc.data.opts&DWG_OPTS_INJSON)?strdup("UNKNOWN_ENT"):const_cast<char*>("UNKNOWN_ENT");
        object.dxfname=(doc.data.opts&DWG_OPTS_IN)?strdup(dxf[record.kind-1]):const_cast<char*>(dxf[record.kind-1]);
        object.klass=&doc.data.dwg_class[object.type-500];
        object.klass->num_instances++;indexes.push_back(index);
    }
    stage="new-network-payloads";for (std::size_t i=0;i<records.size();++i) {
        auto& object=doc.data.object[indexes[i]];const auto& record=records[i];Chain common,handles,text,payload;
        bit_write_BOT(&common.value,object.type);const auto type_bits=bit_position(&common.value);object.bitsize=0;
        require(dwg_encode_entity(&object,&common.value,&handles.value,&text.value)<DWG_ERR_CRITICAL);
        const auto common_end=bit_position(&common.value);
        require(dwg_encode_common_entity_handle_data(&common.value,&handles.value,&object)<DWG_ERR_CRITICAL);
        append(payload.value,record.main,record.main_bits);append(payload.value,record.text,record.text_bits);
        if (record.text_bits) {bit_write_RS(&payload.value,record.text_bits);bit_write_B(&payload.value,1);} else bit_write_B(&payload.value,0);
        object.bitsize=common_end+bit_position(&payload.value);const auto common_handle_bits=bit_position(&handles.value);
        std::vector<unsigned char> common_handles(handles.value.chain,handles.value.chain+(common_handle_bits+7)/8);
        append(payload.value,common_handles,common_handle_bits);
        for (const auto ref:record.references) {
            Dwg_Handle handle{};handle.code=4;handle.value=ref?doc.data.object[indexes[ref-1]].handle.value:0;
            for (auto value=handle.value;value;value>>=8) ++handle.size;
            bit_write_H(&payload.value,&handle);
        }
        while ((common_end+bit_position(&payload.value))%8) bit_write_B(&payload.value,1);
        object.common_size=common_end-type_bits;object.num_unknown_bits=bit_position(&payload.value);object.size=(common_end+object.num_unknown_bits)/8;
        object.has_strings=record.text_bits!=0;object.stringstream_size=record.text_bits;object.handlestream_size=object.size*8-object.bitsize;
        payload.value.byte=0;payload.value.bit=0;object.unknown_bits=bit_read_bits(&payload.value,object.num_unknown_bits);require(object.unknown_bits);
    }
    stage="new-network-write";require(dwg_write_file("derived.dwg",&doc.data)<DWG_ERR_CRITICAL);
}
void apply_edits(Document& doc) {
    EditInput input;const auto count=input.number(4);require(count && count<=10000);
    std::unordered_map<std::uint64_t,Dwg_Object*> objects;
    for (unsigned i=0;i<doc.data.num_objects;++i) objects.emplace(doc.data.object[i].handle.value,&doc.data.object[i]);
    std::unordered_map<unsigned,const char*> classes;
    for (unsigned i=0;i<doc.data.num_classes;++i) classes.emplace(doc.data.dwg_class[i].number,doc.data.dwg_class[i].dxfname);
    std::unordered_set<std::uint64_t> seen;std::size_t total=0;
    for (std::size_t i=0;i<count;++i) {
        const auto handle=input.number(8),before_bits=input.number(4),after_bits=input.number(4);
        require(seen.insert(handle).second && objects.count(handle));auto& object=*objects.at(handle);
        require(classes.count(object.type) && object.num_unknown_bits==before_bits);
        const auto* name=classes.at(object.type);
        require(name && (std::strcmp(name,"RCNODE")==0 || std::strcmp(name,"RCCONDUCTOR")==0 || std::strcmp(name,"RCHEATLOAD")==0 || std::strcmp(name,"RCRECTANGLE")==0 || std::strcmp(name,"RCTD_FDBRICK")==0));
        require(after_bits>=before_bits && (after_bits-before_bits)%64==0 && after_bits-before_bits<=128);
        auto before=input.payload(before_bits);auto after=input.payload(after_bits);total+=before.size()+after.size();require(total<=2*max_payload);
        require(wire_bytes(object.unknown_bits,before_bits)==before);
        if (after_bits%8) {
            unsigned char tail=0;
            for (unsigned j=0;j<after_bits%8;++j) tail|=((after.back()>>(7-j))&1)<<j;
            after.back()=tail;
        }
        auto* replacement=static_cast<unsigned char*>(std::calloc(after.size()+1,1));require(replacement);
        std::memcpy(replacement,after.data(),after.size());std::free(object.unknown_bits);object.unknown_bits=replacement;
        const auto delta=after_bits-before_bits;object.num_unknown_bits=after_bits;object.bitsize+=delta;object.size+=delta/8;
    }
    require(input.cursor==input.bytes.size());
}
void fresh(const char* name) { require(!std::filesystem::exists(name)); }
void load(Document& doc, int& errors) {
    require(std::filesystem::is_regular_file("source.dwg"));
    require(std::filesystem::file_size("source.dwg") <= max_bytes);
    std::ifstream input("source.dwg",std::ios::binary); char signature[6]; input.read(signature,6);
    require(input.gcount()==6 && std::memcmp(signature,"AC1032",6)==0);
    errors=dwg_read_file("source.dwg",&doc.data);
    require(errors < DWG_ERR_CRITICAL);
    require(doc.data.header.version==R_2018 && doc.data.header.from_version==R_2018);
    require(doc.data.num_objects<=100000 && doc.data.num_classes<=10000);
}
void snapshot(Document& doc, int errors) {
    fresh("native.json"); fresh("standard.json");
    auto& data=doc.data;
    std::ofstream out("native.json",std::ios::binary); require(bool(out));
    out << "{\"protocol\":\"" << protocol << "\",\"patch_sha256\":\"" << FCST_PATCH_SHA256
        << "\",\"version\":\"AC1032\",\"opaque_encoding\":\"msb-first-final-byte/1\",\"read_errors\":" << errors
        << ",\"classes\":[";
    for (unsigned i=0; i<data.num_classes; ++i) {
        if (i) out << ',';
        const auto& c=data.dwg_class[i];
        out << "{\"number\":" << c.number << ",\"proxyflag\":" << c.proxyflag << ",\"appname\":";
        class_text(out,c.appname); out << ",\"cppname\":"; class_text(out,c.cppname);
        out << ",\"dxfname\":"; quoted(out,c.dxfname);
        out << ",\"is_zombie\":" << unsigned(c.is_zombie) << ",\"item_class_id\":" << c.item_class_id
            << ",\"num_instances\":" << c.num_instances << ",\"dwg_version\":" << c.dwg_version
            << ",\"maint_version\":" << c.maint_version << ",\"unknown_1\":" << c.unknown_1
            << ",\"unknown_2\":" << c.unknown_2 << '}';
    }
    out << "],\"objects\":[";
    std::size_t total=0;
    for (unsigned i=0; i<data.num_objects; ++i) {
        if (i) out << ',';
        const auto& obj=data.object[i];
        const std::size_t bytes=(std::size_t(obj.num_unknown_bits)+7)/8;
        const std::size_t rest=(std::size_t(obj.num_unknown_rest)+7)/8;
        require(bytes<=max_payload && rest<=max_payload && bytes+rest<=max_payload-total);
        total+=bytes+rest;
        out << "{\"handle\":" << obj.handle.value << ",\"type\":" << obj.type << ",\"kind\":";
        quoted(out,obj.name); out << ",\"bits\":" << obj.num_unknown_bits << ",\"data\":";
        opaque(out,obj.unknown_bits,obj.num_unknown_bits);
        out << ",\"rest_bits\":" << obj.num_unknown_rest << ",\"rest\":";
        opaque(out,obj.unknown_rest,obj.num_unknown_rest);
        out << ",\"object_bits\":" << std::size_t(obj.size)*8 << ",\"common_bits\":" << obj.common_size << ",\"data_bits\":" << obj.bitsize
            << ",\"string_bits\":" << obj.stringstream_size << ",\"handle_bits\":" << obj.handlestream_size << '}';
    }
    require(data.fcst_acds_size<=max_payload-total);
    out << "],\"opaque_sections\":[{\"name\":\"AcDsPrototype_1b\",\"byte_length\":" << data.fcst_acds_size << ",\"data\":";
    hex(out,data.fcst_acds_raw,data.fcst_acds_size); out << "}]}\n";
    out.close(); require(bool(out));
    Bit_Chain chain{};
    chain.version=data.header.version; chain.from_version=data.header.from_version;
    chain.fh=std::fopen("standard.json","wb"); require(chain.fh);
    const int result=dwg_write_json(&chain,&data);
    const int closed=std::fclose(chain.fh);
    require(result < DWG_ERR_CRITICAL && closed==0);
}
void fixture() {
    fresh("source.dwg"); Document doc;
    doc.data.header.version=R_2018; doc.data.header.from_version=R_2018;
    require(dwg_add_Document(&doc.data,0)==0);
    auto* space=dwg_model_space_object(&doc.data);
    require(space && space->tio.object && space->tio.object->tio.BLOCK_HEADER);
    const dwg_point_3d a{0,0,0},b{1,2,3};
    require(dwg_add_LINE(space->tio.object->tio.BLOCK_HEADER,&a,&b));
    require(dwg_add_class(&doc.data,"FCST_OWNED_FIXTURE","FcstOwnedFixture","FCST",false)>=0);
    // This is a synthetic container class, never a simulated TD serialization.
    doc.data.dwg_class[doc.data.num_classes-1].dwg_version=0;
    require(dwg_write_file("source.dwg",&doc.data)<DWG_ERR_CRITICAL);
}
}
int main(int argc,char** argv) {
    try {
        require(argc==2);
        const std::string operation=argv[1];
        if (operation=="--build-info") {
            std::cout << "{\"protocol\":\"" << protocol << "\",\"backend\":\"LibreDWG 0.14\",\"patch_sha256\":\""
                      << FCST_PATCH_SHA256 << "\",\"license\":\"GPL-3.0-or-later\",\"vendor_runtime_required\":false}\n";
            return 0;
        }
        if (operation=="fixture") { fixture(); return 0; }
        if (operation=="create-network") { create_network(); return 0; }
        require(operation=="inspect" || operation=="rewrite" || operation=="rewrite-edited");
        Document doc; int errors=0; load(doc,errors);
        if (operation=="rewrite-edited") apply_edits(doc);
        snapshot(doc,errors);
        if (operation=="rewrite" || operation=="rewrite-edited") {
            fresh("derived.dwg");
            require(dwg_write_file("derived.dwg",&doc.data)<DWG_ERR_CRITICAL);
        }
        return 0;
    } catch (...) {
        std::cerr << "dwg_bridge_operation_failed:" << stage << '\n'; return 2;
    }
}
