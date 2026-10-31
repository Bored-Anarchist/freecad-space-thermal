// SPDX-License-Identifier: MIT OR Apache-2.0
#pragma once
#include "fcst/radiation.hpp"
#include <cmath>

namespace radiation_fixtures {
using namespace fcst::radiation;
inline void square(std::vector<Facet>& fs,std::string id,std::size_t node,Vec3 origin,Vec3 u,Vec3 v,Optics optics={}) {
  auto sum=[](Vec3 a,Vec3 b) { for(int k=0;k<3;++k)a[k]+=b[k]; return a; };
  auto a=origin,b=sum(origin,u),c=sum(sum(origin,u),v),d=sum(origin,v);
  fs.push_back({id+"-a",id,"main",node,{a,b,c},optics,{1,1,false}});
  fs.push_back({id+"-b",id,"main",node,{a,c,d},optics,{1,1,false}});
}
inline std::vector<Facet> plates(std::size_t subdivisions=1) {
  std::vector<Facet> fs; fs.reserve(4*subdivisions*subdivisions);
  double step=1.0/static_cast<double>(subdivisions);
  for(std::size_t i=0;i<subdivisions;++i) for(std::size_t j=0;j<subdivisions;++j) {
    double x=static_cast<double>(i)*step,y=static_cast<double>(j)*step;
    auto offset=fs.size(); square(fs,"lower",0,{x,y,0},{step,0,0},{0,step,0});
    square(fs,"upper",1,{x,y+step,1},{step,0,0},{0,-step,0});
    for(auto k=offset;k<fs.size();++k) fs[k].id+="-"+std::to_string(i)+"-"+std::to_string(j);
  }
  return fs;
}
inline std::vector<Facet> cube() {
  std::vector<Facet> fs;
  square(fs,"bottom",0,{0,0,0},{1,0,0},{0,1,0});
  square(fs,"top",1,{0,1,1},{1,0,0},{0,-1,0});
  square(fs,"left",2,{0,0,0},{0,1,0},{0,0,1});
  square(fs,"right",3,{1,1,0},{0,-1,0},{0,0,1});
  square(fs,"near",4,{1,0,0},{-1,0,0},{0,0,1});
  square(fs,"far",5,{0,1,0},{1,0,0},{0,0,1}); return fs;
}
inline std::vector<Facet> spheres(unsigned refinement=2) {
  using Triangle=std::array<Vec3,3>;
  const Vec3 x{1,0,0},nx{-1,0,0},y{0,1,0},ny{0,-1,0},z{0,0,1},nz{0,0,-1};
  std::vector<Triangle> ts{{x,y,z},{y,nx,z},{nx,ny,z},{ny,x,z},{y,x,nz},{nx,y,nz},{ny,nx,nz},{x,ny,nz}};
  auto midpoint=[](Vec3 a,Vec3 b) { for(int k=0;k<3;++k)a[k]+=b[k]; double n=std::hypot(a[0],a[1],a[2]); for(double& c:a)c/=n;return a; };
  for(unsigned level=0;level<refinement;++level) {
    std::vector<Triangle> next;
    for(const auto& t:ts) {
      auto a=midpoint(t[0],t[1]),b=midpoint(t[1],t[2]),c=midpoint(t[2],t[0]);
      next.push_back({t[0],a,c});next.push_back({a,t[1],b});next.push_back({c,b,t[2]});next.push_back({a,b,c});
    }
    ts=std::move(next);
  }
  std::vector<Facet> fs;
  for(std::size_t i=0;i<ts.size();++i) for(int outer=0;outer<2;++outer) {
    auto t=ts[i]; if(outer) { for(auto& v:t)for(double& c:v)c*=2;std::swap(t[1],t[2]); }
    std::string id=outer?"outer":"inner";
    fs.push_back({id+"-"+std::to_string(i),id,"main",static_cast<std::size_t>(outer),t,{},{1,1,false}});
  }
  return fs;
}
inline Exchange exact_pair(double first=1,double second=1,double f12=1,double f21=1,Optics a={},Optics b={}) {
  constexpr std::uint64_t n=1000000;
  auto h12=static_cast<std::uint64_t>(f12*static_cast<double>(n)),h21=static_cast<std::uint64_t>(f21*static_cast<double>(n));
  return Exchange({{"a/front","a","main",0,false,first,a},{"b/front","b","main",1,false,second,b}},
    {{0,n,n-h12,0,h12?std::vector<Count>{{1,h12}}:std::vector<Count>{}}, {1,n,n-h21,0,h21?std::vector<Count>{{0,h21}}:std::vector<Count>{}}});
}
} // namespace radiation_fixtures
