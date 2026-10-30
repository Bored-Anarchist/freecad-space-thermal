// SPDX-License-Identifier: MIT OR Apache-2.0
#include "fcst/contracts.hpp"
#include "fcst/contract_bundle.hpp"
#include "fcst/thermal.hpp"
#include "fcst/thermal_steady.hpp"
#include "fcst/thermal_schema.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <functional>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <limits>
#include <map>
#include <queue>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <variant>
#include <vector>
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>

namespace fcst {
namespace {
struct Error { std::string code; std::string entity; std::string source; };
[[noreturn]] void fail(std::string code) { throw Error{std::move(code),{}, {}}; }
struct J {
  using A = std::vector<J>;
  using O = std::map<std::string, J>;
  std::variant<std::nullptr_t, bool, double, std::string, A, O> v;
  J() : v(nullptr) {}
  J(bool b) : v(b) {}
  J(double d) : v(d) {}
  J(std::string s) : v(std::move(s)) {}
  J(const char* s) : v(std::string(s)) {}
  J(A a) : v(std::move(a)) {}
  J(O o) : v(std::move(o)) {}
  bool isobj() const { return std::holds_alternative<O>(v); }
  bool isarr() const { return std::holds_alternative<A>(v); }
  bool isstr() const { return std::holds_alternative<std::string>(v); }
  bool isnum() const { return std::holds_alternative<double>(v); }
  const O& obj() const { return std::get<O>(v); }
  O& obj() { return std::get<O>(v); }
  const A& arr() const { return std::get<A>(v); }
  A& arr() { return std::get<A>(v); }
  const std::string& str() const { return std::get<std::string>(v); }
  double num() const { return std::get<double>(v); }
  bool has(const std::string& k) const { return isobj() && obj().contains(k); }
  const J& at(const std::string& k) const { return obj().at(k); }
  J& at(const std::string& k) { return obj().at(k); }
  const J& at(std::size_t i) const { return arr().at(i); }
  bool operator==(const J&) const = default;
};
void utf8(std::string& s, unsigned n) {
  if (n < 0x80) s += static_cast<char>(n);
  else if (n < 0x800) { s += static_cast<char>(0xc0 | (n >> 6)); s += static_cast<char>(0x80 | (n & 63)); }
  else if (n < 0x10000) { s += static_cast<char>(0xe0 | (n >> 12)); s += static_cast<char>(0x80 | ((n >> 6) & 63)); s += static_cast<char>(0x80 | (n & 63)); }
  else { s += static_cast<char>(0xf0 | (n >> 18)); s += static_cast<char>(0x80 | ((n >> 12) & 63)); s += static_cast<char>(0x80 | ((n >> 6) & 63)); s += static_cast<char>(0x80 | (n & 63)); }
}
struct Parser {
  std::string_view s;
  std::size_t p = 0;
  void ws() { while (p < s.size() && (s[p]==' ' || s[p]=='\n' || s[p]=='\r' || s[p]=='\t')) ++p; }
  char take() { if (p >= s.size()) fail("invalid_json"); return s[p++]; }
  unsigned hex4() {
    unsigned n = 0;
    for (int i=0; i<4; ++i) { char c=take(); unsigned x= c>='0' && c<='9' ? static_cast<unsigned>(c-'0') : c>='a' && c<='f' ? static_cast<unsigned>(c-'a'+10) : c>='A' && c<='F' ? static_cast<unsigned>(c-'A'+10) : 16; if (x==16) fail("invalid_json"); n=n*16+x; }
    return n;
  }
  std::string string() {
    if (take()!='"') fail("invalid_json");
    std::string out;
    while (true) {
      char c=take(); if (c=='"') break;
      if (static_cast<unsigned char>(c)<32) fail("invalid_json");
      if (c!='\\') { out+=c; continue; }
      c=take();
      switch(c) {
        case '"': case '\\': case '/': out+=c; break;
        case 'b': out+='\b'; break; case 'f': out+='\f'; break; case 'n': out+='\n'; break; case 'r': out+='\r'; break; case 't': out+='\t'; break;
        case 'u': { unsigned n=hex4(); if (n>=0xd800 && n<=0xdbff) { if (take()!='\\' || take()!='u') fail("invalid_json"); unsigned low=hex4(); if(low<0xdc00 || low>0xdfff) fail("invalid_json"); n=0x10000+((n-0xd800)<<10)+(low-0xdc00); } else if(n>=0xdc00 && n<=0xdfff) fail("invalid_json"); utf8(out,n); break; }
        default: fail("invalid_json");
      }
    }
    return out;
  }
  J value(int depth=0) {
    if(depth>64) fail("invalid_json");
    ws(); if(p>=s.size()) fail("invalid_json"); char c=s[p];
    if(c=='"') return J(string());
    if(c=='{' || c=='[') {
      ++p; bool object=c=='{'; J::O o; J::A a; ws();
      if(p<s.size() && s[p]==(object?'}':']')) { ++p; return object?J(o):J(a); }
      while(true) {
        ws();
        if(object) { auto key=string(); ws(); if(take()!=':') fail("invalid_json"); J x=value(depth+1); if(!o.emplace(key,std::move(x)).second) fail("invalid_json"); }
        else a.push_back(value(depth+1));
        ws(); char sep=take(); if(sep==(object?'}':']')) break; if(sep!=',') fail("invalid_json");
      }
      return object?J(o):J(a);
    }
    for(auto [literal,result] : std::array<std::pair<std::string_view,J>,3>{{{"true",J(true)},{"false",J(false)},{"null",J()}}}) {
      if(s.substr(p,literal.size())==literal) { p+=literal.size(); return result; }
    }
    std::size_t start=p;
    if(s[p]=='-') ++p;
    if(p>=s.size()) fail("invalid_json");
    if(s[p]=='0') ++p;
    else { if(s[p]<'1' || s[p]>'9') fail("invalid_json"); while(p<s.size() && s[p]>='0' && s[p]<='9') ++p; }
    if(p<s.size() && s[p]=='.') { ++p; auto first=p; while(p<s.size() && s[p]>='0' && s[p]<='9') ++p; if(p==first) fail("invalid_json"); }
    if(p<s.size() && (s[p]=='e' || s[p]=='E')) { ++p; if(p<s.size() && (s[p]=='+' || s[p]=='-')) ++p; auto first=p; while(p<s.size() && s[p]>='0' && s[p]<='9') ++p; if(p==first) fail("invalid_json"); }
    double d=0; auto result=std::from_chars(s.data()+start,s.data()+p,d);
    if(result.ec!=std::errc{} || !std::isfinite(d)) fail("invalid_json");
    return J(d);
  }
  J parse() {
    if(s.size()>1048576 || (!s.empty() && MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.data(),static_cast<int>(s.size()),nullptr,0)==0)) fail("invalid_json");
    J j=value(); ws(); if(p!=s.size()) fail("invalid_json"); return j;
  }
};
std::string hex(std::string_view s) {
  constexpr char digits[]="0123456789abcdef"; std::string out; out.reserve(s.size()*2);
  for(unsigned char c:s) { out+=digits[c>>4]; out+=digits[c&15]; } return out;
}
std::string canonical(const J& j) {
  if(std::holds_alternative<std::nullptr_t>(j.v)) return "n";
  if(std::holds_alternative<bool>(j.v)) return std::get<bool>(j.v)?"t":"f";
  if(j.isnum()) {
    auto n=std::bit_cast<std::uint64_t>(j.num()==0?0.0:j.num()); std::string bytes;
    for(int i=7;i>=0;--i) bytes+=static_cast<char>((n>>(i*8))&255);
    return "d"+hex(bytes);
  }
  if(j.isstr()) return "s"+std::to_string(j.str().size())+":"+j.str();
  std::string out;
  if(j.isarr()) { out="a"+std::to_string(j.arr().size())+":"; for(const auto& v:j.arr()) out+=canonical(v); }
  else { out="o"+std::to_string(j.obj().size())+":"; for(const auto& [k,v]:j.obj()) out+=canonical(J(k))+canonical(v); }
  return out;
}
std::string dump(const J& j) {
  if(j.isstr()) {
    std::string out="\"";
    for(unsigned char c:j.str()) { if(c=='"' || c=='\\') {out+='\\';out+=static_cast<char>(c);} else if(c<32) { out+="\\u00"+hex(std::string(1,static_cast<char>(c))); } else out+=static_cast<char>(c); }
    return out+'"';
  }
  if(j.isnum()) { std::ostringstream s; s<<std::setprecision(17)<<j.num(); return s.str(); }
  if(std::holds_alternative<bool>(j.v)) return std::get<bool>(j.v)?"true":"false";
  if(std::holds_alternative<std::nullptr_t>(j.v)) return "null";
  std::string out=j.isarr()?"[":"{"; bool first=true;
  if(j.isarr()) for(const auto& v:j.arr()) { if(!first) out+=','; first=false; out+=dump(v); }
  else for(const auto& [k,v]:j.obj()) { if(!first) out+=','; first=false; out+=dump(J(k))+":"+dump(v); }
  return out+(j.isarr()?"]":"}");
}
const J& bundle() {
  static J b=[] { std::string raw; for(auto part:contract_bundle_parts) raw+=part; return Parser{raw}.parse(); }();
  return b;
}
bool contains(const J& a,const J& v) { return std::find(a.arr().begin(),a.arr().end(),v)!=a.arr().end(); }
void validate(const J& s,const J& j,const J& root,int depth=0,int schema_hops=0) {
  if(depth>64 || schema_hops>64) fail("schema");
  if(s.has("$ref")) { auto r=s.at("$ref").str(); return validate(root.at("$defs").at(r.substr(r.rfind('/')+1)),j,root,depth,schema_hops+1); }
  if(s.has("oneOf")) { int count=0; for(const auto& c:s.at("oneOf").arr()) { try {validate(c,j,root,depth,schema_hops+1);++count;} catch(const Error&) {} } if(count!=1) fail("schema"); return; }
  if(s.has("const") && !(s.at("const")==j)) fail("schema");
  if(s.has("enum") && !contains(s.at("enum"),j)) fail("schema");
  if(!s.has("type")) return;
  auto kind=s.at("type").str();
  if(kind=="object") {
    if(!j.isobj()) fail("schema");
    for(const auto& k:s.at("required").arr()) if(!j.has(k.str())) fail("schema");
    for(const auto& [k,v]:j.obj()) { if(!s.at("properties").has(k)) fail("schema"); validate(s.at("properties").at(k),v,root,depth+1); }
  } else if(kind=="array") {
    if(!j.isarr()) fail("schema"); auto size=static_cast<double>(j.arr().size());
    if((s.has("minItems") && size<s.at("minItems").num()) || (s.has("maxItems") && size>s.at("maxItems").num())) fail("schema");
    std::set<std::string> items;
    for(const auto& v:j.arr()) { validate(s.at("items"),v,root,depth+1); if(s.has("uniqueItems") && !items.insert(canonical(v)).second) fail("schema"); }
  } else if(kind=="string") {
    if(!j.isstr()) fail("schema");
    auto size=static_cast<double>(std::count_if(j.str().begin(),j.str().end(),[](unsigned char c){return (c&0xc0)!=0x80;}));
    if((s.has("minLength") && size<s.at("minLength").num()) || (s.has("maxLength") && size>s.at("maxLength").num())) fail("schema");
    if(s.has("pattern") && !std::regex_match(j.str(),std::regex(s.at("pattern").str()))) fail("schema");
  } else if(kind=="boolean") { if(!std::holds_alternative<bool>(j.v)) fail("schema"); }
  else if(kind=="number" || kind=="integer") {
    if(!j.isnum() || !std::isfinite(j.num())) fail("schema");
    if(kind=="integer" && std::floor(j.num())!=j.num()) fail("schema");
    if((s.has("minimum") && j.num()<s.at("minimum").num()) || (s.has("maximum") && j.num()>s.at("maximum").num()) || (s.has("exclusiveMinimum") && j.num()<=s.at("exclusiveMinimum").num())) fail("schema");
  } else fail("schema");
}
J normalize(J j) {
  if(j.isarr()) for(auto& v:j.arr()) v=normalize(v);
  else if(j.isobj()) {
    if(j.obj().size()==2 && j.has("value") && j.has("unit")) {
      const auto& unit=bundle().at("units").at(j.at("unit").str());
      double n=j.at("value").num()*unit.at(1).num()+unit.at(2).num(); if(!std::isfinite(n)) fail("range");
      if(unit.at(0).str()=="temperature" && n<0) fail("range");
      j.at("value")=J(n==0?0.0:n); j.at("unit")=bundle().at("si").at(unit.at(0).str());
    } else try { for(auto& [k,v]:j.obj()) { (void)k; v=normalize(v); } }
      catch(Error& e) { if(j.has("id") && j.has("kind")) e.entity=j.at("id").str(); throw; }
  }
  return j;
}
std::string dimension(const J& q) {return bundle().at("units").at(q.at("unit").str()).at(0).str();}
double quantity(const J& q,const std::string& dim,double minimum=-std::numeric_limits<double>::infinity(),bool strict=false) {
  if(dimension(q)!=dim) fail("dimension"); auto n=q.at("value").num(); if(n<minimum || (strict && n==minimum)) fail("range"); return n;
}
using Entities=std::map<std::string,J>;
const J& target(const Entities& es,const std::string& id,const std::string& kinds) {
  auto it=es.find(id); if(it==es.end() || (" "+kinds+" ").find(" "+it->second.at("kind").str()+" ")==std::string::npos) fail("reference"); return it->second;
}
double det(const J& r) {
  double out=0; for(std::size_t i=0;i<3;++i) out+=r.at(0).at(i).num()*(r.at(1).at((i+1)%3).num()*r.at(2).at((i+2)%3).num()-r.at(1).at((i+2)%3).num()*r.at(2).at((i+1)%3).num()); return out;
}
using Graph=std::map<std::string,std::set<std::string>>;
std::vector<std::string> dependency_order(const Graph& graph,const std::string& limit_code,bool entity_context=false) {
  std::map<std::string,std::vector<std::string>> parents;
  std::map<std::string,std::size_t> remaining,heights;
  auto reject=[&](const std::string& code,const std::string& key) {throw Error{code,entity_context?key:"",{}};};
  for(const auto& [key,children]:graph) {remaining[key]=children.size();heights[key]=1;}
  for(const auto& [key,children]:graph) for(const auto& child:children) {
    if(!graph.contains(child)) reject("reference",key);
    parents[child].push_back(key);
  }
  std::priority_queue<std::string,std::vector<std::string>,std::greater<std::string>> ready;
  for(const auto& [key,count]:remaining) if(count==0) ready.push(key);
  std::vector<std::string> order;
  while(!ready.empty()) {
    auto child=ready.top();ready.pop();order.push_back(child);
    for(const auto& parent:parents[child]) {
      heights[parent]=std::max(heights[parent],heights[child]+1);
      if(--remaining[parent]==0) ready.push(parent);
    }
  }
  if(order.size()!=graph.size()) for(const auto& [key,count]:remaining) if(count!=0) reject("cycle",key);
  for(const auto& [key,height]:heights) if(height>64) reject(limit_code,key);
  return order;
}
void expression_symbols(const J& ast,std::set<std::string>& symbols) {
  auto op=ast.at("op").str();
  if(op=="symbol") symbols.insert(ast.at("expression_id").str());
  else if(op=="table") expression_symbols(ast.at("input"),symbols);
  else if(ast.has("args")) for(const auto& child:ast.at("args").arr()) expression_symbols(child,symbols);
}
struct Expressions {
  const Entities& es;
  std::map<std::string,std::string> visited;
  std::string id(const std::string& key) {
    return visited.at(key);
  }
  std::string infer(const J& ast) {
    auto op=ast.at("op").str();
    if(op=="literal") return dimension(ast.at("quantity"));
    if(op=="symbol") return id(ast.at("expression_id").str());
    if(op=="table") {
      const auto& x=ast.at("x"); const auto& y=ast.at("y"); auto xd=dimension(x.at(0)),yd=dimension(y.at(0));
      if(x.arr().size()!=y.arr().size()) fail("expression");
      for(std::size_t i=0;i<x.arr().size();++i) { if(i+1<x.arr().size() && x.at(i).at("value").num()>=x.at(i+1).at("value").num()) fail("expression"); quantity(x.at(i),xd); quantity(y.at(i),yd); }
      if(infer(ast.at("input"))!=xd) fail("dimension");
      for(const auto& i:ast.at("discontinuities").arr()) if(i.num()<1 || i.num()>=static_cast<double>(x.arr().size())) fail("expression");
      if(!ast.at("discontinuities").arr().empty() && ast.at("interpolation").str()!="previous") fail("expression");
      return yd;
    }
    std::vector<std::string> args; for(const auto& a:ast.at("args").arr()) args.push_back(infer(a));
    bool unary=op=="negate" || op=="abs" || op=="sqrt" || op=="exp" || op=="log" || op=="sin" || op=="cos";
    if(args.size()!=(unary?1u:2u)) fail("expression");
    auto a=args[0];
    if(op=="add" || op=="subtract" || op=="min" || op=="max") {
      auto b=args[1];
      if(op=="subtract" && a=="temperature" && b==a) return "temperature_difference";
      if(op=="add" && ((a=="temperature" && b=="temperature_difference") || (b=="temperature" && a=="temperature_difference"))) return "temperature";
      if(op=="subtract" && a=="temperature" && b=="temperature_difference") return "temperature";
      if(a!=b || (a=="temperature" && (op=="add" || op=="subtract"))) fail("dimension"); return a;
    }
    if(std::find(args.begin(),args.end(),"temperature")!=args.end()) fail("dimension");
    if(op=="negate" || op=="abs") return a;
    if(op=="exp" || op=="log" || op=="sin" || op=="cos") { if(a!="scalar" && !((op=="sin" || op=="cos") && a=="angle")) fail("dimension"); return "scalar"; }
    J::A ds;
    for(std::size_t i=0;i<4;++i) { double n=bundle().at("dimensions").at(a).at(i).num(); ds.emplace_back(op=="sqrt"?n/2:n+(op=="multiply"?1:-1)*bundle().at("dimensions").at(args[1]).at(i).num()); }
    for(const auto& [name,d]:bundle().at("dimensions").obj()) if(name!="temperature" && name!="angle" && d==J(ds)) return name;
    fail("dimension");
  }
};
void check_model(const J& m) {
  Entities es; std::set<std::string> ids{m.at("project_id").str()};
  for(auto key:{"entities","source_maps","mappings","attachments"}) for(const auto& e:m.at(key).arr()) {
    if(!ids.insert(e.at("id").str()).second) fail("duplicate_id"); if(std::string_view(key)=="entities") es.emplace(e.at("id").str(),e);
  }
  const std::map<std::string,std::string> refs={{"submodel_id","submodel"},{"frame_id","frame"},{"geometry_id","geometry"},{"mesh_id","mesh"},{"material_id","material"},{"optics_id","optics"},{"from_node_id","node"},{"to_node_id","node"},{"node_id","node"},{"sensor_node_id","node"},{"load_id","load"},{"environment_id","environment"},{"expression_id","expression"}};
  const std::map<std::string,std::pair<std::string,double>> fields={{"temperature",{"temperature",0}},{"capacity",{"capacity",0}},{"conductance",{"conductance",0}},{"power",{"power",-INFINITY}},{"density",{"density",0}},{"specific_heat",{"specific_heat",0}},{"conductivity",{"conductivity",0}},{"area",{"area",0}},{"background_temperature",{"temperature",0}},{"solar_flux",{"flux",0}},{"start",{"time",-INFINITY}},{"end",{"time",-INFINITY}},{"time_origin",{"time",-INFINITY}},{"on_below",{"temperature",0}},{"off_above",{"temperature",0}}};
  for(const auto& [eid,e]:es) {
    try {
    auto kind=e.at("kind").str();
    for(const auto& [k,v]:e.obj()) {
      if(refs.contains(k)) target(es,v.str(),refs.at(k));
      if(fields.contains(k)) quantity(v,fields.at(k).first,fields.at(k).second);
    }
    for(auto [key,kinds]:std::array<std::pair<std::string,std::string>,4>{{{"facet_ids","facet"},{"excluded_facet_ids","facet"},{"load_ids","load"},{"control_ids","control"}}}) if(e.has(key)) for(const auto& v:e.at(key).arr()) target(es,v.str(),kinds);
    if(e.has("parent_id")) {
      std::set<std::string> seen{eid}; const J* cursor=&e;
      while(cursor->has("parent_id")) { auto parent=cursor->at("parent_id").str(); if(!seen.insert(parent).second) fail("cycle"); cursor=&target(es,parent,kind); }
    }
    if(kind=="node" && ((e.at("classification").str()=="capacitive")!=(e.at("capacity").at("value").num()>0))) fail("range");
    if(kind=="conductor" && e.at("from_node_id")==e.at("to_node_id")) fail("reference");
    if((kind=="face" || kind=="facet") && e.at("area").at("value").num()<=0) fail("range");
    if(kind=="frame") {
      for(const auto& q:e.at("origin").arr()) quantity(q,"length");
      const auto& r=e.at("rotation");
      for(std::size_t i=0;i<3;++i) for(std::size_t j=0;j<3;++j) { double dot=0; for(std::size_t k=0;k<3;++k) dot+=r.at(i).at(k).num()*r.at(j).at(k).num(); if(std::abs(dot-(i==j?1:0))>1e-12) fail("frame"); }
      if(std::abs(det(r)-1)>1e-12) fail("frame");
    }
    if((kind=="facet" || kind=="element") && target(es,e.at("mesh_id").str(),"mesh").at("role").str()!=(kind=="facet"?"radiation":"conduction")) fail("reference");
    if(kind=="material") {
      auto lo=quantity(e.at("valid_temperature").at(0),"temperature",0),hi=quantity(e.at("valid_temperature").at(1),"temperature",0);
      if(lo>=hi || e.at("density").at("value").num()<=0 || e.at("specific_heat").at("value").num()<=0 || e.at("conductivity").at("value").num()<=0) fail("range");
      if(e.has("conductivity_tensor")!=e.has("frame_id")) fail("frame");
      if(e.has("conductivity_tensor")) { const auto& t=e.at("conductivity_tensor"); for(std::size_t i=0;i<3;++i) for(std::size_t j=0;j<3;++j) if(t.at(i).at(j)!=t.at(j).at(i)) fail("range"); double a=t.at(0).at(1).num(); double minor=t.at(0).at(0).num()*t.at(1).at(1).num()-a*a; if(t.at(0).at(0).num()<=0 || !std::isfinite(minor) || minor<=0 || !std::isfinite(det(t)) || det(t)<=0) fail("range"); }
    }
    if(kind=="optics") { for(auto k:{"solar_absorptivity","ir_emissivity","specular_fraction","transmissivity"}) if(e.at(k).num()>1) fail("range"); if(e.at("specular_fraction").num()+e.at("transmissivity").num()>1) fail("range"); }
    if(kind=="case") {
      if(e.at("start").at("value").num()>e.at("end").at("value").num()) fail("range");
      for(const auto& o:e.at("overlays").arr()) { const auto& t=target(es,o.at("entity_id").str(),"node load conductor"); auto field=o.at("field").str(); if(!t.has(field)) fail("reference"); quantity(o.at("value"),fields.at(field).first,fields.at(field).second); }
    }
    if(kind=="control" && e.at("on_below").at("value").num()>=e.at("off_above").at("value").num()) fail("range");
    if(kind=="load" && e.has("expression_id") && target(es,e.at("expression_id").str(),"expression").at("dimension").str()!="power") fail("dimension");
    } catch(Error& error) {
      error.entity=eid;
      for(const auto& source:m.at("source_maps").arr()) for(const auto& entry:source.at("entries").arr()) if(entry.at("entity_id").str()==eid && error.source.empty()) error.source=source.at("id").str();
      throw;
    }
  }
  std::string kinds; for(const auto& k:bundle().at("entity_kinds").arr()) kinds+=k.str()+" ";
  for(const auto& s:m.at("source_maps").arr()) {
    std::set<std::pair<std::string,std::string>> keys;
    for(const auto& e:s.at("entries").arr()) { target(es,e.at("entity_id").str(),kinds); if(!keys.emplace(e.at("namespace").str(),e.at("handle").str()).second) fail("duplicate_id"); }
  }
  std::set<std::pair<std::string,std::string>> pairs; std::map<std::pair<std::string,std::string>,double> weights;
  auto mappings=m.at("mappings").arr(); std::sort(mappings.begin(),mappings.end(),[](const J& a,const J& b){return a.at("id").str()<b.at("id").str();});
  for(const auto& map:mappings) {
    auto a=map.at("from_id").str(),b=map.at("to_id").str(); const auto& from=target(es,a,"face facet element node"); const auto& to=target(es,b,"face facet element node");
    auto ak=from.at("kind").str(),bk=to.at("kind").str();
    if(!((ak=="face" && (bk=="facet" || bk=="element")) || ((ak=="facet" || ak=="element") && bk=="node"))) fail("reference");
    if(!pairs.emplace(a,b).second) fail("duplicate_id"); quantity(map.at("area"),"area",0,true); weights[{a,bk}]+=map.at("weight").num();
  }
  for(const auto& [k,w]:weights) { (void)k; if(std::abs(w-1)>1e-12) fail("range"); }
  for(const auto& a:m.at("attachments").arr()) {
    target(es,a.at("entity_id").str(),"facet element load"); const auto& f=target(es,a.at("face_id").str(),"face"); const auto& g=target(es,f.at("geometry_id").str(),"geometry");
    if(a.at("state").str()!="resolved" || a.at("source_revision")!=g.at("revision") || a.at("persistent_ref")!=f.at("persistent_ref") || a.at("signature")!=f.at("signature")) fail("attachment");
  }
  Expressions expressions{es,{}};
  Graph graph;
  for(const auto& [id,e]:es) if(e.at("kind").str()=="expression") expression_symbols(e.at("ast"),graph[id]);
  try {
    for(const auto& id:dependency_order(graph,"expression",true)) {
      try {
        const auto& e=es.at(id);
        auto dimension=expressions.infer(e.at("ast"));
        if(dimension!=e.at("dimension").str()) fail("dimension");
        expressions.visited[id]=dimension;
      } catch(Error& error) {error.entity=id;throw;}
    }
  } catch(Error& error) {
    for(const auto& source:m.at("source_maps").arr()) for(const auto& entry:source.at("entries").arr()) if(entry.at("entity_id").str()==error.entity && error.source.empty()) error.source=source.at("id").str();
    throw;
  }
}
void artifacts(const J& j) {
  if(j.isarr()) for(const auto& v:j.arr()) artifacts(v);
  if(!j.isobj()) return;
  if(j.obj().size()==3 && j.has("path") && j.has("sha256") && j.has("byte_length")) {
    std::istringstream input(j.at("path").str()); std::string part;
    if(j.at("path").str().back()=='/') fail("artifact");
    while(std::getline(input,part,'/')) {
      if(part.empty() || part=="." || part==".." || part.back()=='.' || part.back()==' ') fail("artifact");
      auto base=part.substr(0,part.find('.')); std::transform(base.begin(),base.end(),base.begin(),[](unsigned char c){return static_cast<char>(std::toupper(c));});
      if(std::regex_match(base,std::regex("CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]"))) fail("artifact");
    }
  }
  for(const auto& [k,v]:j.obj()) { (void)k; artifacts(v); }
}
std::string sha256(const std::string& bytes);
#include "spatial.inc"
J read(const std::string& kind,J j) {
  if(!j.isobj()) fail("schema");
  J version((kind=="spatial" || kind=="manifest2")?"2.0.0":"1.0.0");
  if(!j.has("contract_version") || j.at("contract_version")!=version || (j.has("minimum_reader") && j.at("minimum_reader")!=version)) fail("version");
  if(kind=="operation" && (!j.has("operation") || !contains(bundle().at("operations"),j.at("operation")))) fail("unsupported_operation");
  if(!bundle().at("schemas").has(kind)) fail("schema"); const auto& schema=bundle().at("schemas").at(kind); validate(schema,j,schema);
  try { j=normalize(j); } catch(Error& error) {
    if(kind=="model" && !error.entity.empty()) for(const auto& source:j.at("source_maps").arr()) for(const auto& entry:source.at("entries").arr()) if(entry.at("entity_id").str()==error.entity && error.source.empty()) error.source=source.at("id").str();
    throw;
  }
  artifacts(j);
  if(kind=="model") check_model(j);
  if(kind=="spatial") check_spatial(j);
  if(kind=="manifest" || kind=="manifest2") {
    std::map<std::string,J> by_id; std::set<std::string> paths;
    for(const auto& r:j.at("artifacts").arr()) {
      auto path=r.at("artifact").at("path").str(); std::transform(path.begin(),path.end(),path.begin(),[](unsigned char c){return static_cast<char>(std::tolower(c));});
      if(!by_id.emplace(r.at("id").str(),r).second || !paths.insert(path).second) fail("duplicate_id");
    }
    auto model=j.at("model_artifact_id").str(); if(!by_id.contains(model) || by_id.at(model).at("role").str()!="model") fail("reference");
    Graph graph;
    for(const auto& [key,v]:by_id) {
      auto& children=graph[key];
      for(const auto& child:v.at("dependencies").arr()) children.insert(child.str());
    }
    dependency_order(graph,"artifact");
  }
  if(kind=="operation") {
    auto op=j.at("operation").str(); auto& args=j.at("arguments");
    if(op=="model.hash" || op=="model.validate") args.at("snapshot")=read("model",args.at("snapshot"));
    if(op=="thermal.conductor.create") { quantity(args.at("conductance"),"conductance",0); std::set<std::string> ids{args.at("id").str(),args.at("from_node_id").str(),args.at("to_node_id").str()}; if(ids.size()!=3) fail("reference"); }
  }
  if(kind=="worker" && j.at("type").str()=="terminal" && ((j.at("payload").at("outcome").str()=="succeeded")!=j.at("payload").has("result"))) fail("artifact");
  if(kind=="worker" && j.at("type").str()=="checkpoint") quantity(j.at("payload").at("time"),"time");
  return j;
}
J snapshot(J m) {
  for(auto key:{"audit","gui","revision"}) m.obj().erase(key);
  for(auto key:{"entities","source_maps","mappings","attachments"}) std::sort(m.at(key).arr().begin(),m.at(key).arr().end(),[](const J& a,const J& b){return a.at("id").str()<b.at("id").str();});
  for(auto& s:m.at("source_maps").arr()) std::sort(s.at("entries").arr().begin(),s.at("entries").arr().end(),[](const J& a,const J& b){ for(auto k:{"namespace","handle","entity_id"}) if(a.at(k)!=b.at(k)) return a.at(k).str()<b.at(k).str(); return false; });
  for(auto& e:m.at("entities").arr()) for(auto key:{"facet_ids","excluded_facet_ids","load_ids","control_ids"}) if(e.has(key)) std::sort(e.at(key).arr().begin(),e.at(key).arr().end(),[](const J& a,const J& b){return a.str()<b.str();});
  return m;
}
std::string sha256(const std::string& bytes) {
  std::array<unsigned char,32> digest{};
  auto status=BCryptHash(BCRYPT_SHA256_ALG_HANDLE,nullptr,0,reinterpret_cast<PUCHAR>(const_cast<char*>(bytes.data())),static_cast<ULONG>(bytes.size()),digest.data(),static_cast<ULONG>(digest.size()));
  if(status<0) fail("artifact"); return hex(std::string_view(reinterpret_cast<const char*>(digest.data()),digest.size()));
}
#include "thermal_loading.inc"
} // namespace
thermal::Model thermal::load(std::string_view input) {
  try { return Model(thermal_data(input)); }
  catch (const fcst::Error& e) { throw thermal::Error(e.code, e.entity, e.source); }
  catch (const thermal::Error&) { throw; }
  catch (const std::exception&) { throw thermal::Error("schema"); }
}
std::string thermal::inspect(std::string_view input) {
  try {
    auto model = thermal::load(input);
    const auto& data = model.data();
    J::A nodes, components;
    for (const auto& node : data.nodes) {
      auto index = [](const std::optional<std::size_t>& i) { return i ? J(static_cast<double>(*i)) : J(); };
      nodes.emplace_back(J::O{{"id", J(node.id)}, {"equation", index(node.equation)},
        {"differential_index", index(node.differential_index)}, {"algebraic_index", index(node.algebraic_index)},
        {"classification", J(node.classification == thermal::NodeClass::capacitive ? "capacitive" :
          node.classification == thermal::NodeClass::algebraic ? "algebraic" : "prescribed")}});
    }
    for (const auto& component : data.components) {
      J::A ids;
      for (auto i : component.nodes) ids.emplace_back(data.nodes.at(i).id);
      components.emplace_back(J::O{{"node_ids", J(ids)}, {"prescribed_anchor", J(component.prescribed_anchor)},
        {"storage_anchor", J(component.storage_anchor)},
        {"steady_conduction_singular", J(component.steady_conduction_singular)},
        {"transient_algebraic_singular", J(component.transient_algebraic_singular)}});
    }
    return dump(J(J::O{{"status", J("passed")}, {"solver_available", J(false)},
      {"model_hash", J(data.model_hash)}, {"preparation_hash", J(data.preparation_hash)},
      {"nodes", J(nodes)}, {"components", J(components)},
      {"material_count", J(static_cast<double>(data.materials.size()))},
      {"source_identity_count", J(static_cast<double>(data.source_identities.size()))},
      {"deferred_entity_count", J(static_cast<double>(data.deferred_entity_ids.size()))}}));
  } catch (const thermal::Error& e) {
    J::O out{{"status", J("failed")}, {"code", J(e.code)}};
    if (!e.entity_id.empty()) out.emplace("entity_id", J(e.entity_id));
    if (!e.source_map_id.empty()) out.emplace("source_map_id", J(e.source_map_id));
    return dump(J(out));
  }
}
std::string thermal::inspect_steady(std::string_view input) {
  try {
    auto model=thermal::load(input); auto model_hash=model.data().model_hash, preparation_hash=model.data().preparation_hash;
    thermal::Assembly assembly(std::move(model)); auto result=thermal::solve_steady(assembly);
    J::A nodes,scales;
    if (result.balance) for (std::size_t i=0;i<assembly.model().data().nodes.size();++i) {
      const auto& node=assembly.model().data().nodes[i];
      nodes.emplace_back(J::O{{"node_id",J(node.id)},{"temperature_K",J(result.balance->temperature[i])},
        {"residual_W",node.equation?J(result.balance->residual[*node.equation]):J()},
        {"boundary_power_W",J(result.balance->boundary_power[i])}});
    }
    for (double v:result.residual_limits) scales.emplace_back(v);
    J::O out{{"status",J(result.solve.status==thermal::SolveStatus::converged?"passed":"failed")},
      {"outcome",J(std::string(thermal::status_code(result.solve.status)))},
      {"reason",J(std::string(thermal::reason_code(result.solve.diagnostics.reason)))},
      {"model_hash",J(model_hash)},{"preparation_hash",J(preparation_hash)},
      {"iterations",J(static_cast<double>(result.solve.iterations))},
      {"evaluations",J(static_cast<double>(result.solve.diagnostics.evaluations))},
      {"rejected_trials",J(static_cast<double>(result.solve.diagnostics.rejected_trials))},
      {"scaled_residual_norm",result.solve.residual_norm?J(*result.solve.residual_norm):J()},
      {"scaled_correction_norm",result.solve.diagnostics.correction_norm?J(*result.solve.diagnostics.correction_norm):J()},
      {"energy_defect_W",result.balance?J(result.balance->energy_defect):J()},
      {"internal_exchange_defect_W",result.balance?J(result.balance->internal_exchange_defect):J()},
      {"residual_limits_W",J(scales)},{"nodes",J(nodes)}};
    if (!result.entity_id.empty()) out.emplace("entity_id",J(result.entity_id));
    if (!result.source_map_id.empty()) out.emplace("source_map_id",J(result.source_map_id));
    return dump(J(out));
  } catch (const thermal::Error& e) {
    J::O out{{"status",J("failed")},{"code",J(e.code)}};
    if (!e.entity_id.empty()) out.emplace("entity_id",J(e.entity_id));
    if (!e.source_map_id.empty()) out.emplace("source_map_id",J(e.source_map_id));
    return dump(J(out));
  } catch (...) { return "{\"status\":\"failed\",\"code\":\"unavailable\"}"; }
}
int run_worker(const std::string& root, const std::string& job_id) {
  // Durable steady result publication is not implemented in this protocol yet.
  // The separate native steady API/CLI does not fabricate a job result artifact.
  try {
    if (!std::regex_match(job_id,std::regex("[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"))) fail("schema");
    auto emit=[&](const J& message) {
      auto bytes=dump(read("worker",message));
      if(bytes.empty() || bytes.size()>65536) fail("schema");
      auto n=static_cast<std::uint32_t>(bytes.size());
      for(unsigned i=0;i<4;++i) std::cout.put(static_cast<char>((n>>(8*i))&255));
      std::cout.write(bytes.data(),static_cast<std::streamsize>(bytes.size())); std::cout.flush();
    };
    auto message=[&](const char* type,double sequence,J payload) {
      return J(J::O{{"contract_version",J("1.0.0")},{"type",J(type)},{"job_id",J(job_id)},
                    {"sequence",J(sequence)},{"payload",std::move(payload)}});
    };
    emit(message("handshake",0,J(J::O{{"capabilities",J(J::O{
      {"contract_version",J("1.0.0")},{"minimum_reader",J("1.0.0")},
      {"operations",J(J::A{J("job.submit"),J("job.cancel")})},
      {"solver_available",J(false)},{"execution_mode",J("fcst_native")}})}})));
    std::uint32_t length=0;
    for(unsigned i=0;i<4;++i) { auto c=std::cin.get(); if(c==EOF) fail("invalid_json"); length|=static_cast<std::uint32_t>(static_cast<unsigned char>(c))<<(8*i); }
    if(length==0 || length>65536) fail("invalid_json");
    std::string bytes(length,'\0'); std::cin.read(bytes.data(),length);
    if(static_cast<std::uint32_t>(std::cin.gcount())!=length) fail("invalid_json");
    auto submit=read("worker",Parser{bytes}.parse());
    if(submit.at("type").str()!="submit" || submit.at("job_id").str()!=job_id || submit.at("sequence").num()!=1) fail("reference");
    const auto& payload=submit.at("payload"); const auto& ref=payload.at("snapshot");
    std::filesystem::path base=std::filesystem::absolute(root), path=base;
    // The authorized artifact root is set by the trusted launcher. Reject
    // reparse points and hard links before opening any model file.
    if((GetFileAttributesW(base.c_str()) & FILE_ATTRIBUTE_REPARSE_POINT)!=0) fail("artifact");
    for(const auto& part:std::filesystem::path(ref.at("path").str())) {
      path/=part;
      auto attributes=GetFileAttributesW(path.c_str());
      if(attributes==INVALID_FILE_ATTRIBUTES || (attributes & FILE_ATTRIBUTE_REPARSE_POINT)!=0) fail("artifact");
    }
    auto size=std::filesystem::file_size(path);
    if(size>1048576 || static_cast<double>(size)!=ref.at("byte_length").num() || std::filesystem::hard_link_count(path)!=1) fail("artifact");
    std::ifstream input(path,std::ios::binary); std::string model_bytes(static_cast<std::size_t>(size),'\0');
    input.read(model_bytes.data(),static_cast<std::streamsize>(size));
    if(static_cast<std::uintmax_t>(input.gcount())!=size || sha256(model_bytes)!=ref.at("sha256").str()) fail("artifact");
    auto model=read("model",Parser{model_bytes}.parse());
    if(sha256(std::string("FCST-semantic-v1\0",17)+canonical(snapshot(model)))!=payload.at("semantic_hash").str()) fail("artifact");
    bool found=false;
    for(const auto& entity:model.at("entities").arr()) if(entity.at("kind").str()=="case" && entity.at("id")==payload.at("case_id")) found=true;
    if(!found) fail("reference");
    emit(message("diagnostic",2,J(J::O{{"code",J("not_implemented")},{"pointer",J("")}})));
    emit(message("terminal",3,J(J::O{{"outcome",J("failed")}})));
    return 0;
  } catch(...) {
    // Malformed input disconnects without success; no paths or model text leak.
    return 2;
  }
}
std::string inspect_contract(std::string_view kind,std::string_view input) {
  try {
    if(kind=="worker-frame") {
      if(input.size()<4) fail("invalid_json");
      std::uint32_t n=0; for(unsigned i=0;i<4;++i) n|=static_cast<std::uint32_t>(static_cast<unsigned char>(input[i]))<<(8*i);
      if(n==0 || n>65536 || input.size()!=static_cast<std::size_t>(n)+4) fail("invalid_json");
      input.remove_prefix(4); kind="worker";
    }
    auto value=read(std::string(kind),Parser{input}.parse()); auto semantic=kind=="model"?snapshot(value):value; auto bytes=canonical(semantic);
    return dump(J(J::O{{"status",J("passed")},{"normalized",value},{"canonical",J(hex(bytes))},{"semantic_hash",J(sha256(std::string("FCST-semantic-v1\0",17)+bytes))}}));
  } catch(const Error& e) {
    J::O out{{"status",J("failed")},{"code",J(e.code)}};
    if(!e.entity.empty()) {out.emplace("entity_id",J(e.entity));out.emplace("pointer",J("/entities"));if(!e.source.empty()) out.emplace("source_map_id",J(e.source));}
    return dump(J(out));
  }
  catch(const std::exception&) {return "{\"status\":\"failed\",\"code\":\"schema\"}";}
}
} // namespace fcst
