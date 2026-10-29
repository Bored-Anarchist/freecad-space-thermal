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
extern "C" {
#include <dwg.h>
#include <dwg_api.h>
#include <out_json.h>
}
#undef restrict

#ifndef FCST_PATCH_SHA256
#define FCST_PATCH_SHA256 "unset"
#endif

namespace {
constexpr const char* protocol = "fcst-dwg-native/1";
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
        << "\",\"version\":\"AC1032\",\"read_errors\":" << errors
        << ",\"classes\":[";
    for (unsigned i=0; i<data.num_classes; ++i) {
        if (i) out << ',';
        const auto& c=data.dwg_class[i];
        out << "{\"number\":" << c.number << ",\"proxyflag\":" << c.proxyflag << ",\"appname\":";
        quoted(out,c.appname); out << ",\"cppname\":"; quoted(out,c.cppname);
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
        hex(out,obj.unknown_bits,bytes);
        out << ",\"rest_bits\":" << obj.num_unknown_rest << ",\"rest\":";
        hex(out,obj.unknown_rest,rest); out << '}';
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
        require(operation=="inspect" || operation=="rewrite");
        Document doc; int errors=0; load(doc,errors); snapshot(doc,errors);
        if (operation=="rewrite") {
            fresh("derived.dwg");
            require(dwg_write_file("derived.dwg",&doc.data)<DWG_ERR_CRITICAL);
        }
        return 0;
    } catch (...) {
        std::cerr << "dwg_bridge_operation_failed\n"; return 2;
    }
}
