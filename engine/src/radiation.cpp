// SPDX-License-Identifier: MIT OR Apache-2.0
#include "fcst/radiation.hpp"
#include <algorithm>
#include <cmath>
#include <numeric>
#include <numbers>
#include <set>

namespace fcst::radiation {
namespace {
using thermal::Error;
double checked(double x) { if (!std::isfinite(x)) throw Error("radiation_range"); return x; }
Vec3 add(Vec3 a,Vec3 b) { for (int k=0;k<3;++k) a[k]+=b[k]; return a; }
Vec3 sub(Vec3 a,Vec3 b) { for (int k=0;k<3;++k) a[k]-=b[k]; return a; }
Vec3 mul(Vec3 a,double s) { for (double& x:a) x*=s; return a; }
double dot(Vec3 a,Vec3 b) { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }
Vec3 cross(Vec3 a,Vec3 b) { return {a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]}; }
double norm(Vec3 a) { return checked(std::hypot(a[0],a[1],a[2])); }
Vec3 normal(const Facet& f) { auto n=cross(sub(f.vertices[1],f.vertices[0]),sub(f.vertices[2],f.vertices[0])); return mul(n,1/norm(n)); }
void optics(const Optics& o) {
  if (!std::isfinite(o.solar_absorptance) || !std::isfinite(o.ir_emittance) ||
      o.solar_absorptance<0 || o.solar_absorptance>1 || o.ir_emittance<0 || o.ir_emittance>1)
    throw Error("radiation_optics");
  const auto& d=o.dataset;
  if(d.solar_band.empty() || d.infrared_band.empty() || d.solar_band==d.infrared_band || d.provenance.empty() ||
     !std::isfinite(d.minimum_temperature) || !std::isfinite(d.maximum_temperature) || d.minimum_temperature<0 || d.maximum_temperature<=d.minimum_temperature ||
     (d.condition!="BOL" && d.condition!="EOL" && d.condition!="unspecified")) throw Error("radiation_optics");
  for(double x:d.absolute_uncertainty) if(!std::isfinite(x) || x<0 || x>1) throw Error("radiation_optics");
}
void patch_check(const Patch& p) {
  optics(p.optics);
  if (p.id.empty() || p.surface_id.empty() || !p.optics.active || !std::isfinite(p.area) || p.area<=0)
    throw Error("radiation_mapping");
}
// SplitMix64's fully specified integer permutation, with a specified 53-bit map.
std::uint64_t mix(std::uint64_t x) {
  x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL; x=(x^(x>>27))*0x94d049bb133111ebULL; return x^(x>>31);
}
struct Random {
  std::uint64_t state;
  double next() { state+=0x9e3779b97f4a7c15ULL; return static_cast<double>(mix(state)>>11)*0x1.0p-53; }
};
std::uint64_t identity(std::string_view id) {
  std::uint64_t h=14695981039346656037ULL;
  for (unsigned char c:id) { h^=c; h*=1099511628211ULL; } return h;
}
constexpr double sigma=5.670374419e-8;
double emission(double t) {
  if (!std::isfinite(t) || t<0) throw Error("radiation_temperature");
  return checked(sigma*t*t*t*t);
}
}
struct Mesh::Impl {
  struct Box { Vec3 lo,hi; };
  struct BuildFacet { Box bounds; Vec3 centroid; };
  struct Tree { Box box; std::size_t begin,end,left=0,right=0; };
  std::vector<Facet> facets;
  std::vector<Patch> patches;
  std::vector<std::array<std::optional<std::size_t>,2>> mapping;
  std::vector<std::vector<std::pair<std::size_t,double>>> members;
  std::vector<std::size_t> order;
  std::vector<Tree> tree;
  static Box box(const Facet& f) {
    Box b{f.vertices[0],f.vertices[0]};
    for (const auto& v:f.vertices) for (int k=0;k<3;++k) { b.lo[k]=std::min(b.lo[k],v[k]); b.hi[k]=std::max(b.hi[k],v[k]); }
    return b;
  }
  std::size_t build(std::size_t begin,std::size_t end,const std::vector<BuildFacet>& geometry) {
    Box b=geometry[order[begin]].bounds;
    for (auto i=begin+1;i<end;++i) { const auto& a=geometry[order[i]].bounds; for (int k=0;k<3;++k) { b.lo[k]=std::min(b.lo[k],a.lo[k]); b.hi[k]=std::max(b.hi[k],a.hi[k]); } }
    auto index=tree.size(); tree.push_back({b,begin,end});
    if (end-begin>8) {
      int axis=0; for (int k=1;k<3;++k) if (b.hi[k]-b.lo[k]>b.hi[axis]-b.lo[axis]) axis=k;
      auto middle=begin+(end-begin)/2;
      std::nth_element(order.begin()+static_cast<std::ptrdiff_t>(begin),order.begin()+static_cast<std::ptrdiff_t>(middle),order.begin()+static_cast<std::ptrdiff_t>(end),[&](auto i,auto j) {
        double x=geometry[i].centroid[axis],y=geometry[j].centroid[axis];
        return x==y ? i<j : x<y;
      });
      auto left=build(begin,middle,geometry),right=build(middle,end,geometry); tree[index].left=left; tree[index].right=right;
    }
    return index;
  }
  static bool intersects(const Box& b,const Ray& ray,double maximum) {
    double lo=0,hi=maximum;
    for (int k=0;k<3;++k) {
      if (ray.direction[k]==0) { if (ray.origin[k]<b.lo[k] || ray.origin[k]>b.hi[k]) return false; }
      else {
        double a=(b.lo[k]-ray.origin[k])/ray.direction[k],c=(b.hi[k]-ray.origin[k])/ray.direction[k];
        if (a>c) std::swap(a,c);
        lo=std::max(lo,a); hi=std::min(hi,c); if (lo>hi) return false;
      }
    }
    return true;
  }
};
Mesh::Mesh(std::vector<Facet> facets,std::vector<std::string> excluded) {
  if (facets.empty() || facets.size()>2000000) throw Error("radiation_limit");
  auto p=std::make_shared<Impl>();
  // Sort small indices rather than repeatedly moving facets and their optical metadata.
  std::vector<std::size_t> sorted(facets.size()); std::iota(sorted.begin(),sorted.end(),0);
  std::sort(sorted.begin(),sorted.end(),[&](auto a,auto b) { return facets[a].id<facets[b].id; });
  std::set<std::string> exclusions(excluded.begin(),excluded.end());
  if (exclusions.size()!=excluded.size()) throw Error("duplicate_id");
  // Validate even excluded geometry. Exclusions remove it from tracing explicitly.
  for (std::size_t position=0;position<sorted.size();++position) {
    const auto& f=facets[sorted[position]];
    if (f.id.empty() || f.surface_id.empty() || (position && f.id==facets[sorted[position-1]].id)) throw Error("radiation_mapping");
    for (auto v:f.vertices) for (double x:v) if (!std::isfinite(x) || std::abs(x)>1e12) throw Error("radiation_geometry");
    double area=norm(cross(sub(f.vertices[1],f.vertices[0]),sub(f.vertices[2],f.vertices[0])))/2;
    if (area<=1e-24) throw Error("radiation_geometry");
    optics(f.front); optics(f.back);
  }
  for (const auto& id:exclusions) {
    auto found=std::lower_bound(sorted.begin(),sorted.end(),id,[&](auto i,const auto& value) { return facets[i].id<value; });
    if (found==sorted.end() || facets[*found].id!=id) throw Error("reference");
  }
  p->facets.reserve(facets.size()-exclusions.size());
  for (auto i:sorted) if (!exclusions.contains(facets[i].id)) p->facets.push_back(std::move(facets[i]));
  if (p->facets.empty()) throw Error("radiation_mapping");
  std::map<std::string,std::size_t> by_id;
  p->mapping.resize(p->facets.size());
  for (std::size_t i=0;i<p->facets.size();++i) {
    const auto& f=p->facets[i]; double area=norm(cross(sub(f.vertices[1],f.vertices[0]),sub(f.vertices[2],f.vertices[0])))/2;
    for (int side=0;side<2;++side) {
      const auto& o=side ? f.back : f.front; if (!o.active) continue;
      std::string id=f.surface_id+(side?"/back":"/front");
      if (!by_id.contains(id)) {
        by_id[id]=p->patches.size(); p->patches.push_back({id,f.surface_id,f.group,f.node,side!=0,0,o}); p->members.emplace_back();
      }
      auto j=by_id.at(id); auto& patch=p->patches[j];
      if (patch.node!=f.node || patch.group!=f.group || patch.optics.ir_emittance!=o.ir_emittance || patch.optics.solar_absorptance!=o.solar_absorptance || patch.optics.dataset!=o.dataset)
        throw Error("radiation_mapping");
      patch.area=checked(patch.area+area); p->mapping[i][side]=j; p->members[j].emplace_back(i,patch.area);
    }
  }
  if (p->patches.empty()) throw Error("radiation_mapping");
  if (exclusions.empty()) p->order=std::move(sorted);
  p->order.resize(p->facets.size()); std::iota(p->order.begin(),p->order.end(),0);
  // Bounds and centroid arithmetic are invariant across every partition level.
  // This scratch data is released after construction, not retained in mesh storage.
  std::vector<Impl::BuildFacet> geometry; geometry.reserve(p->facets.size());
  for (const auto& f:p->facets) {
    Vec3 centroid{}; for (int k=0;k<3;++k) centroid[k]=(f.vertices[0][k]+f.vertices[1][k]+f.vertices[2][k])/3;
    geometry.push_back({Impl::box(f),centroid});
  }
  p->tree.reserve(p->facets.size()/2+1); p->build(0,p->facets.size(),geometry); impl_=p;
}
const std::vector<Facet>& Mesh::facets() const { return impl_->facets; }
const std::vector<Patch>& Mesh::patches() const { return impl_->patches; }
std::optional<std::size_t> Mesh::patch(std::size_t i,bool back) const {
  if (i>=impl_->mapping.size()) throw Error("radiation_mapping");
  return impl_->mapping[i][back?1:0];
}
std::size_t Mesh::storage_bytes() const {
  std::size_t size=sizeof(Impl)+impl_->facets.capacity()*sizeof(Facet)+impl_->tree.capacity()*sizeof(Impl::Tree)+
    impl_->order.capacity()*sizeof(std::size_t)+impl_->mapping.capacity()*sizeof(impl_->mapping[0]);
  auto metadata_bytes=[](const Optics& o) { const auto& d=o.dataset;return d.solar_band.capacity()+d.infrared_band.capacity()+d.condition.capacity()+d.provenance.capacity(); };
  for (const auto& f:impl_->facets) size+=f.id.capacity()+f.surface_id.capacity()+f.group.capacity()+metadata_bytes(f.front)+metadata_bytes(f.back);
  size+=impl_->patches.capacity()*sizeof(Patch)+impl_->members.capacity()*sizeof(impl_->members[0]);
  for (const auto& m:impl_->members) size+=m.capacity()*sizeof(m[0]);
  for (const auto& p:impl_->patches) size+=p.id.capacity()+p.surface_id.capacity()+p.group.capacity()+metadata_bytes(p.optics);
  return size;
}
std::optional<Hit> Mesh::intersect(const Ray& r,std::optional<std::size_t> ignore) const {
  for (int k=0;k<3;++k) if (!std::isfinite(r.origin[k]) || !std::isfinite(r.direction[k])) throw Error("radiation_ray");
  if (std::abs(norm(r.direction)-1)>1e-12 || (ignore && *ignore>=facets().size())) throw Error("radiation_ray");
  std::optional<Hit> best;
  // Median splits and the two-million-facet limit bound depth below 20.
  // Avoid a heap allocation on every sampled ray; preserve traversal/tie order.
  std::array<std::size_t,64> stack; stack[0]=0; std::size_t pending=1;
  while (pending) {
    auto index=stack[--pending]; const auto& tree=impl_->tree[index];
    if (!Impl::intersects(tree.box,r,best?best->distance:std::numeric_limits<double>::infinity())) continue;
    if (tree.left) {
      if (pending+2>stack.size()) throw Error("radiation_limit");
      stack[pending++]=tree.right; stack[pending++]=tree.left; continue;
    }
    for (auto j=tree.begin;j<tree.end;++j) {
      auto i=impl_->order[j]; if (ignore && i==*ignore) continue;
      const auto& f=facets()[i]; auto e1=sub(f.vertices[1],f.vertices[0]),e2=sub(f.vertices[2],f.vertices[0]);
      auto h=cross(r.direction,e2); double det=dot(e1,h);
      if (std::abs(det)<=1e-14*norm(e1)*norm(e2)) continue;
      auto s=sub(r.origin,f.vertices[0]); double u=dot(s,h)/det;
      auto q=cross(s,e1); double v=dot(r.direction,q)/det;
      if (u<0 || v<0 || u+v>1) continue;
      double distance=dot(e2,q)/det;
      if (distance>0 && (!best || distance<best->distance || (distance==best->distance && i<best->facet))) best=Hit{i,det<0,distance};
    }
  }
  return best;
}
struct Sampler {
  static Row row(const Mesh& mesh,std::size_t source,const Sampling& settings,const IntersectionBackend* backend) {
    if (source>=mesh.patches().size() || !settings.samples || settings.samples>1000000000 || !settings.maximum_entries) throw Error("radiation_limit");
    const auto& patch=mesh.patches()[source]; Random random{mix(settings.seed)^identity(patch.id)};
    const auto& members=mesh.impl_->members[source]; std::map<std::size_t,std::uint64_t> counts;
    Row row{source,settings.samples,0,0,{}};
    for (std::uint64_t n=0;n<settings.samples;++n) {
      double selection=random.next()*patch.area;
      auto member=std::upper_bound(members.begin(),members.end(),selection,[](double v,const auto& entry) { return v<entry.second; });
      if (member==members.end()) member=members.end()-1;
      auto i=member->first; const auto& f=mesh.facets()[i];
      double a=std::sqrt(random.next()),b=random.next();
      auto origin=add(mul(f.vertices[0],1-a),add(mul(f.vertices[1],a*(1-b)),mul(f.vertices[2],a*b)));
      auto normal_=mul(normal(f),patch.back?-1:1);
      Vec3 axis=std::abs(normal_[0])<.8 ? Vec3{1,0,0}:Vec3{0,1,0};
      auto tangent=cross(axis,normal_); tangent=mul(tangent,1/norm(tangent)); auto bitangent=cross(normal_,tangent);
      double radial=std::sqrt(random.next()),angle=2*std::numbers::pi*random.next();
      auto direction=add(mul(normal_,std::sqrt(1-radial*radial)),add(mul(tangent,radial*std::cos(angle)),mul(bitangent,radial*std::sin(angle))));
      // Offset by representable coordinates toward the emitting hemisphere.
      for (int k=0;k<3;++k) if (normal_[k]!=0) origin[k]=std::nextafter(origin[k],normal_[k]>0?std::numeric_limits<double>::infinity():-std::numeric_limits<double>::infinity());
      auto hit=(backend?*backend:static_cast<const IntersectionBackend&>(mesh)).intersect({origin,direction},i);
      if (!hit) { ++row.escaped; continue; }
      auto target=mesh.patch(hit->facet,hit->back);
      if (!target || mesh.patches()[*target].group!=patch.group) { ++row.blocked; continue; }
      if (!counts.contains(*target) && counts.size()>=settings.maximum_entries) throw Error("radiation_limit");
      ++counts[*target];
    }
    for (auto [j,hits]:counts) row.counts.push_back({j,hits});
    return row;
  }
};
Row trace_row(const Mesh& mesh,std::size_t source,const Sampling& s,const IntersectionBackend* backend) { return Sampler::row(mesh,source,s,backend); }
Interval wilson(std::uint64_t hits,std::uint64_t samples,double z) {
  if (!samples || hits>samples || !std::isfinite(z) || z<=0) throw Error("radiation_statistics");
  double n=static_cast<double>(samples),p=static_cast<double>(hits)/n,d=1+z*z/n;
  double center=(p+z*z/(2*n))/d,half=z*std::sqrt(p*(1-p)/n+z*z/(4*n*n))/d;
  return {p,std::max(0.0,center-half),std::min(1.0,center+half)};
}
Exchange::Exchange(std::vector<Patch> patches,std::vector<Row> rows,std::size_t maximum_edges)
    : patches_(std::move(patches)),raw_(std::move(rows)) {
  if (patches_.empty() || raw_.size()!=patches_.size() || !maximum_edges) throw Error("radiation_mapping");
  std::set<std::string> ids;
  for (const auto& p:patches_) { patch_check(p); if (!ids.insert(p.id).second) throw Error("duplicate_id"); }
  std::sort(raw_.begin(),raw_.end(),[](const auto& a,const auto& b) { return a.source<b.source; });
  std::map<std::pair<std::size_t,std::size_t>,std::array<double,2>> pairs;
  for (std::size_t i=0;i<raw_.size();++i) {
    const auto& row=raw_[i]; if (row.source!=i || !row.samples || row.samples>1000000000 || row.escaped>row.samples || row.blocked>row.samples-row.escaped) throw Error("radiation_statistics");
    std::uint64_t total=row.escaped+row.blocked; std::set<std::size_t> targets;
    for (const auto& count:row.counts) {
      auto j=count.target;
      if (j>=patches_.size() || !count.hits || count.hits>row.samples-total || !targets.insert(j).second || patches_[i].group!=patches_[j].group) throw Error("radiation_statistics");
      total+=count.hits; auto key=std::minmax(i,j);
      if (!pairs.contains(key) && pairs.size()>=maximum_edges) throw Error("radiation_limit");
      pairs[key][i<=j?0:1]=patches_[i].area*static_cast<double>(count.hits)/static_cast<double>(row.samples);
      ++diagnostics_.raw_entries;
    }
    diagnostics_.maximum_raw_closure=std::max(diagnostics_.maximum_raw_closure,std::abs(1-static_cast<double>(total)/static_cast<double>(row.samples)));
    if (total!=row.samples) throw Error("radiation_closure");
  }
  std::vector<double> sums(patches_.size());
  for (auto [key,values]:pairs) {
    auto [i,j]=key; double g=i==j?values[0]:(values[0]+values[1])/2;
    if(i!=j) diagnostics_.maximum_raw_reciprocity=std::max(diagnostics_.maximum_raw_reciprocity,std::abs(values[0]-values[1])/std::max(patches_[i].area,patches_[j].area));
    edges_.push_back({i,j,g}); sums[i]+=g; if (i!=j) sums[j]+=g;
  }
  // Reciprocal row-cap projection: symmetric pair averaging followed by the
  // smaller endpoint row scale. Unallocated power goes to the explicit reservoir.
  std::vector<double> scale(sums.size(),1);
  for (std::size_t i=0;i<sums.size();++i) if (sums[i]>patches_[i].area) scale[i]=patches_[i].area/sums[i];
  for (auto& e:edges_) e.area_factor*=std::min(scale[e.first],scale[e.second]);
  // For an entirely closed ensemble, restore closure by symmetric diagonal
  // balancing. No silent escape is introduced; nonconvergence fails explicitly.
  bool closed=std::all_of(raw_.begin(),raw_.end(),[](const auto& r) { return r.escaped==0 && r.blocked==0; });
  if (closed) {
    bool converged=false;
    for (std::size_t step=0;step<10000;++step) {
      std::fill(sums.begin(),sums.end(),0);
      for (const auto& e:edges_) { sums[e.first]+=e.area_factor; if(e.first!=e.second) sums[e.second]+=e.area_factor; }
      double defect=0;
      for (std::size_t i=0;i<sums.size();++i) {
        if (sums[i]<=0) throw Error("radiation_closure");
        scale[i]=std::sqrt(patches_[i].area/sums[i]); defect=std::max(defect,std::abs(sums[i]/patches_[i].area-1));
      }
      if (defect<1e-12) { converged=true; break; }
      for (auto& e:edges_) e.area_factor*=scale[e.first]*scale[e.second];
    }
    if (!converged) throw Error("radiation_closure");
  }
  std::fill(sums.begin(),sums.end(),0);
  for (const auto& e:edges_) { sums[e.first]+=e.area_factor; if(e.first!=e.second) sums[e.second]+=e.area_factor; }
  escape_.resize(sums.size());
  for (std::size_t i=0;i<sums.size();++i) escape_[i]=closed?0:std::max(0.0,1-sums[i]/patches_[i].area);
  for (const auto& e:edges_) {
    auto values=pairs.at({e.first,e.second});
    diagnostics_.maximum_correction=std::max(diagnostics_.maximum_correction,std::abs(e.area_factor-values[0])/patches_[e.first].area);
    if(e.first!=e.second) diagnostics_.maximum_correction=std::max(diagnostics_.maximum_correction,std::abs(e.area_factor-values[1])/patches_[e.second].area);
  }
}
std::vector<Edge> Exchange::page(std::size_t offset,std::size_t limit) const {
  if (offset>edges_.size() || limit>4096) throw Error("radiation_limit");
  auto count=std::min(limit,edges_.size()-offset);
  return {edges_.begin()+static_cast<std::ptrdiff_t>(offset),edges_.begin()+static_cast<std::ptrdiff_t>(offset+count)};
}
Exchange trace(const Mesh& mesh,const Sampling& settings) {
  std::vector<Row> rows; std::size_t entries=0;
  for(std::size_t i=0;i<mesh.patches().size();++i) {
    auto row=trace_row(mesh,i,settings); entries+=row.counts.size();
    if(entries>settings.maximum_entries) throw Error("radiation_limit");
    rows.push_back(std::move(row));
  }
  return Exchange(mesh.patches(),std::move(rows),settings.maximum_entries);
}
namespace {
std::vector<double> incident(const Exchange& e,std::span<const double> j) {
  std::vector<double> h(j.size());
  for (const auto& edge:e.edges()) {
    auto a=edge.first,b=edge.second; h[a]+=edge.area_factor/e.patches()[a].area*j[b];
    if(a!=b) h[b]+=edge.area_factor/e.patches()[b].area*j[a];
  }
  return h;
}
std::vector<double> solve(const Exchange& e,std::span<const double> rhs,bool solar,const RadiosityOptions& o,std::size_t& iterations,double& defect) {
  std::vector<double> j(rhs.size(),0);
  double scale=1; for (double x:rhs) scale=std::max(scale,std::abs(checked(x)));
  // Contractive fixed point. Perfect mirrors are supported if the operator
  // contracts through absorption/escape; closed perfect-mirror systems reject.
  for (std::size_t k=0;k<o.maximum_iterations;++k) {
    auto h=incident(e,j); double error=0;
    for (std::size_t i=0;i<j.size();++i) {
      double a=solar?e.patches()[i].optics.solar_absorptance:e.patches()[i].optics.ir_emittance;
      double next=checked(rhs[i]+(1-a)*h[i]); error=std::max(error,std::abs(next-j[i])); h[i]=next;
    }
    j.swap(h); ++iterations;
    if(error<=o.tolerance*scale) {
      auto check=incident(e,j); double residual=0;
      for (std::size_t i=0;i<j.size();++i) {
        double a=solar?e.patches()[i].optics.solar_absorptance:e.patches()[i].optics.ir_emittance;
        residual=std::max(residual,std::abs(j[i]-rhs[i]-(1-a)*check[i]));
      }
      defect=std::max(defect,residual);
      if(residual<=o.tolerance*scale) return j;
    }
  }
  throw Error("radiation_nonconverged");
}
void options(const Exchange& e,const RadiosityOptions& o) {
  (void)emission(o.background_temperature);
  if(!std::isfinite(o.tolerance) || o.tolerance<=0 || o.tolerance>1e-4 || !o.maximum_iterations || o.maximum_iterations>1000000 ||
    (!o.solar_incident.empty() && o.solar_incident.size()!=e.patches().size())) throw Error("radiation_options");
  for(double x:o.solar_incident) if(!std::isfinite(x) || x<0) throw Error("radiation_options");
  // A zero source does not prove uniqueness in a perfectly reflecting cavity.
  for(bool solar:{false,true}) {
    if(solar && o.solar_incident.empty()) continue;
    std::vector<bool> reachable(e.patches().size());
    for(std::size_t i=0;i<reachable.size();++i) reachable[i]=e.escape()[i]>0 ||
      (solar?e.patches()[i].optics.solar_absorptance:e.patches()[i].optics.ir_emittance)>0;
    for(std::size_t step=0;step<reachable.size();++step) {
      bool changed=false;
      for(const auto& edge:e.edges()) if(edge.area_factor>0 && reachable[edge.first]!=reachable[edge.second]) { reachable[edge.first]=reachable[edge.second]=true; changed=true; }
      if(!changed) break;
    }
    if(std::find(reachable.begin(),reachable.end(),false)!=reachable.end()) throw Error("radiation_singular");
  }
}
struct Powers { std::vector<double> internal_power,environment; };
Powers powers(const Exchange& e,std::span<const double> j,double background,std::span<const double> solar={}) {
  Powers p{std::vector<double>(j.size()),std::vector<double>(j.size())};
  for(const auto& edge:e.edges()) if(edge.first!=edge.second) {
    double q=checked(edge.area_factor*(j[edge.second]-j[edge.first])); p.internal_power[edge.first]+=q; p.internal_power[edge.second]-=q;
  }
  for(std::size_t i=0;i<j.size();++i) p.environment[i]=checked(e.patches()[i].area*e.escape()[i]*(background-j[i])+(solar.empty()?0:solar[i]));
  return p;
}
}
Evaluation evaluate(const Exchange& e,std::span<const double> t,const RadiosityOptions& o) {
  options(e,o); for(double x:t) (void)emission(x);
  auto n=e.patches().size(); double background=emission(o.background_temperature); std::vector<double> rhs(n);
  for(std::size_t i=0;i<n;++i) {
    const auto& p=e.patches()[i]; if(p.node>=t.size()) throw Error("radiation_mapping");
    if(t[p.node]<p.optics.dataset.minimum_temperature || t[p.node]>p.optics.dataset.maximum_temperature) throw Error("radiation_optical_domain");
    rhs[i]=p.optics.ir_emittance*emission(t[p.node])+(1-p.optics.ir_emittance)*e.escape()[i]*background;
  }
  Evaluation result; result.radiosity=solve(e,rhs,false,o,result.iterations,result.linear_defect);
  std::vector<double> solar(n);
  if(!o.solar_incident.empty()) {
    for(std::size_t i=0;i<n;++i) rhs[i]=(1-e.patches()[i].optics.solar_absorptance)*o.solar_incident[i];
    result.solar_radiosity=solve(e,rhs,true,o,result.iterations,result.linear_defect); auto h=incident(e,result.solar_radiosity);
    for(std::size_t i=0;i<n;++i) solar[i]=checked(e.patches()[i].area*e.patches()[i].optics.solar_absorptance*(h[i]+o.solar_incident[i]));
  }
  auto p=powers(e,result.radiosity,background,solar); result.internal_power=std::move(p.internal_power); result.environment=std::move(p.environment);
  return result;
}
std::vector<thermal::PowerBinding> bind(std::shared_ptr<const Exchange> exchange,std::string radiation_id,std::string environment_id,RadiosityOptions o,std::size_t maximum) {
  if(!exchange || radiation_id.empty() || environment_id.empty() || radiation_id==environment_id) throw Error("radiation_mapping");
  options(*exchange,o); std::set<std::size_t> node_set;
  for(const auto& p:exchange->patches()) node_set.insert(p.node);
  std::vector<std::size_t> nodes(node_set.begin(),node_set.end());
  if(!maximum || nodes.size()>maximum/nodes.size()) throw Error("radiation_limit");
  std::vector<thermal::Entry> dependencies;
  for(auto i:nodes) for(auto j:nodes) dependencies.push_back({i,j});
  auto callback=[exchange,o,nodes,dependencies](bool external,double,std::span<const double> t,bool jacobian) {
    auto result=evaluate(*exchange,t,o); thermal::PowerEvaluation out{std::vector<double>(nodes.size()),{}};
    std::map<std::size_t,std::size_t> index; for(std::size_t k=0;k<nodes.size();++k) index[nodes[k]]=k;
    for(std::size_t i=0;i<exchange->patches().size();++i) out.watts[index.at(exchange->patches()[i].node)]+=external?result.environment[i]:result.internal_power[i];
    if(jacobian) {
      out.d_temperature.resize(dependencies.size());
      for(std::size_t column=0;column<nodes.size();++column) {
        std::vector<double> rhs(exchange->patches().size());
        for(std::size_t i=0;i<rhs.size();++i) if(exchange->patches()[i].node==nodes[column]) rhs[i]=checked(4*sigma*exchange->patches()[i].optics.ir_emittance*std::pow(t[nodes[column]],3));
        std::size_t iterations=0; double defect=0; auto j=solve(*exchange,rhs,false,o,iterations,defect); auto p=powers(*exchange,j,0);
        for(std::size_t i=0;i<j.size();++i) out.d_temperature[index.at(exchange->patches()[i].node)*nodes.size()+column]+=external?p.environment[i]:p.internal_power[i];
      }
    }
    return out;
  };
  return {{std::move(radiation_id),thermal::PowerKind::radiation,nodes,dependencies,[callback](double time,std::span<const double> t,bool jac) { return callback(false,time,t,jac); }},
    {std::move(environment_id),thermal::PowerKind::environment,nodes,dependencies,[callback](double time,std::span<const double> t,bool jac) { return callback(true,time,t,jac); }}};
}
} // namespace fcst::radiation
