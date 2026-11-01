// SPDX-License-Identifier: MIT OR Apache-2.0
#include "radiation_fixtures.hpp"
#include "fcst/thermal_transient.hpp"
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <numeric>

using namespace fcst;
using namespace radiation;
using namespace radiation_fixtures;
namespace {
void require(bool ok) { if(!ok) throw std::runtime_error("acceptance_failed"); }
void near(double x,double y,double tolerance=1e-8) { require(std::isfinite(x) && std::abs(x-y)<=tolerance*std::max(1.0,std::abs(y))); }
template<class F> void rejects(F f) { try { f(); } catch(const thermal::Error&) { return; } throw std::runtime_error("expected_rejection"); }
std::string uid(unsigned n) { auto s=std::to_string(n);return "00000000-0000-4000-8000-"+std::string(12-s.size(),'0')+s; }
thermal::Model model(const std::filesystem::path& root) {
  std::ifstream f(root/"power-network.json"); return thermal::load(std::string(std::istreambuf_iterator<char>(f),{}));
}
double sum(const std::vector<double>& v) { return std::accumulate(v.begin(),v.end(),0.0); }
// Flat scan checks BVH partition/bounds decisions independently of its traversal.
std::optional<Hit> flat_hit(const std::vector<Facet>& facets,const Ray& ray,std::optional<std::size_t> ignore={}) {
  auto subtract=[](Vec3 a,Vec3 b) { for(int k=0;k<3;++k)a[k]-=b[k];return a; };
  auto product=[](Vec3 a,Vec3 b) { return Vec3{a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]}; };
  auto scalar=[](Vec3 a,Vec3 b) { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; };
  std::optional<Hit> best;
  for(std::size_t i=0;i<facets.size();++i) {
    if(ignore && i==*ignore)continue;
    const auto& f=facets[i];auto a=subtract(f.vertices[1],f.vertices[0]),b=subtract(f.vertices[2],f.vertices[0]);
    auto n=product(a,b);double denominator=scalar(n,ray.direction);
    if(denominator==0)continue;
    double distance=scalar(n,subtract(f.vertices[0],ray.origin))/denominator;
    if(distance<=0)continue;
    Vec3 point=ray.origin;for(int k=0;k<3;++k)point[k]+=distance*ray.direction[k];
    bool inside=true;
    for(int k=0;k<3;++k) {
      auto edge=subtract(f.vertices[(k+1)%3],f.vertices[k]);
      if(scalar(product(edge,subtract(point,f.vertices[k])),n)<0)inside=false;
    }
    if(inside && (!best || distance<best->distance || (distance==best->distance && i<best->facet)))
      best=Hit{i,denominator>0,distance};
  }
  return best;
}
}
int main(int argc,char** argv) {
  try {
    require(argc==3);std::string name=argv[1];std::filesystem::path root=argv[2];
    if(name=="intersections") {
      Mesh mesh(plates()); auto h=mesh.intersect({{.25,.4,-1},{0,0,1}});require(h && h->back);near(h->distance,1);
      h=mesh.intersect({{.25,.4,.5},{0,0,1}});require(h && !h->back);near(h->distance,.5);
      h=mesh.intersect({{.25,.4,.5},{0,0,-1}});require(h && !h->back);near(h->distance,.5);
      require(!mesh.intersect({{2,.5,.5},{0,0,1}}));require(!mesh.intersect({{.5,.5,-1},{1,0,0}}));
      auto edge=mesh.intersect({{.5,.5,-1},{0,0,1}});require(edge.has_value());near(edge->distance,1);
      rejects([&]{mesh.intersect({{0,0,0},{0,0,0}});});rejects([&]{mesh.intersect({{0,0,0},{0,0,2}});});
      Mesh dense(plates(20));for(int i=1;i<20;++i) { auto hit=dense.intersect({{static_cast<double>(i)/20+.001,.373,-1},{0,0,1}});require(hit.has_value());near(hit->distance,1); }
    } else if(name=="bvh-equivalence") {
      for(int axis=0;axis<3;++axis) {
        auto fs=plates(9);auto overlap=fs.front();overlap.id="tie-first";fs.push_back(overlap);
        for(auto& f:fs)for(auto& v:f.vertices)std::rotate(v.begin(),v.begin()+axis,v.end());
        std::reverse(fs.begin(),fs.end());
        std::vector<std::string> excluded{fs[7].id,fs[19].id};Mesh mesh(fs,excluded);
        std::erase_if(fs,[&](const auto& f){return std::find(excluded.begin(),excluded.end(),f.id)!=excluded.end();});
        std::sort(fs.begin(),fs.end(),[](const auto& a,const auto& b){return a.id<b.id;});
        require(mesh.facets().size()==fs.size());
        for(std::size_t i=0;i<fs.size();++i)require(mesh.facets()[i].id==fs[i].id);
        for(int x=-1;x<=10;++x)for(int y=-1;y<=10;++y)for(int side=0;side<2;++side) {
          Ray ray{{(static_cast<double>(x)+.25)/9,(static_cast<double>(y)+.625)/9,side?2.0:-1.0},{0,0,side?-1.0:1.0}};
          std::rotate(ray.origin.begin(),ray.origin.begin()+axis,ray.origin.end());
          std::rotate(ray.direction.begin(),ray.direction.begin()+axis,ray.direction.end());
          auto expected=flat_hit(fs,ray),actual=mesh.intersect(ray);require(actual.has_value()==expected.has_value());
          if(actual){require(actual->facet==expected->facet && actual->back==expected->back);near(actual->distance,expected->distance);
            auto next=flat_hit(fs,ray,actual->facet),ignored=mesh.intersect(ray,actual->facet);require(next.has_value()==ignored.has_value());
            if(next){require(next->facet==ignored->facet && next->back==ignored->back);near(next->distance,ignored->distance);}}
        }
      }
    } else if(name=="geometry-mapping") {
      auto fs=plates();auto invalid=fs;invalid[0].vertices[1]=invalid[0].vertices[0];rejects([&]{Mesh m(invalid);});
      invalid=fs;invalid[0].id=invalid[1].id;rejects([&]{Mesh m(invalid);});invalid=fs;invalid[0].node=2;rejects([&]{Mesh m(invalid);});
      invalid=fs;invalid[0].front.ir_emittance=1.1;rejects([&]{Mesh m(invalid);});
      invalid=fs;invalid[0].vertices[0][0]=std::numeric_limits<double>::quiet_NaN();rejects([&]{Mesh m(invalid);});
      rejects([&]{Mesh m(fs,{"missing"});});
      Mesh mesh(fs);near(mesh.patches()[0].area,1);near(mesh.patches()[1].area,1);
      fs[0].back={.2,.3,true};fs[1].back=fs[0].back;Mesh two(fs);require(two.patches().size()==3);
      auto r=trace_row(two,1,{17,512,100});require(r.escaped==512); // lower back sees space
      Mesh excluded(fs,{fs[2].id,fs[3].id});require(excluded.facets().size()==2);
      for(std::size_t i=0;i<excluded.patches().size();++i) require(trace_row(excluded,i,{17,512,100}).escaped==512);
      auto both=trace(excluded,{17,512,100});auto value=evaluate(both,std::vector<double>{300,300},{200,1e-12,100,{100,100}});
      near(sum(value.environment),1.3*5.670374419e-8*(std::pow(200.,4)-std::pow(300.,4))+120);
    } else if(name=="seed-streams") {
      auto fs=plates();Mesh a(fs);auto first=trace_row(a,0,{1701,4096,100});std::reverse(fs.begin(),fs.end());Mesh b(fs);
      auto second=trace_row(b,0,{1701,4096,100});require(first.counts[0].hits==second.counts[0].hits);
      auto future=std::async(std::launch::async,[&]{return trace_row(a,0,{1701,4096,100});});
      (void)trace_row(a,1,{1701,4096,100});require(future.get().counts[0].hits==first.counts[0].hits);
      require(trace_row(a,0,{2903,4096,100}).counts[0].hits!=first.counts[0].hits);
      auto i=wilson(20,100,1.959963984540054);near(i.estimate,.2);require(i.lower<.2 && i.upper>.2);
      near(wilson(0,100,2).lower,0);near(wilson(100,100,2).upper,1);rejects([]{wilson(101,100,2);});
    } else if(name=="occlusion-groups") {
      auto fs=plates();square(fs,"blocker",2,{-10,-10,.5},{20,0,0},{0,20,0});fs[4].front.active=false;fs[5].front.active=false;
      Mesh blocked(fs);auto source=std::find_if(blocked.patches().begin(),blocked.patches().end(),[](const auto& p){return p.surface_id=="lower";})-blocked.patches().begin();
      auto r=trace_row(blocked,static_cast<std::size_t>(source),{1701,4096,100});require(r.counts.empty() && r.blocked>4000);
      fs=plates();for(auto& f:fs)if(f.surface_id=="upper")f.group="other";auto x=trace(Mesh(fs),{1701,4096,100});
      require(x.edges().empty() && x.raw()[0].blocked>0);near(x.escape()[0],1);
    } else if(name=="exchange-correction") {
      Mesh mesh(plates());auto e=trace(mesh,{1701,4096,100});require(e.diagnostics().maximum_correction>0);
      for(const auto& edge:e.edges()) { require(edge.area_factor>=0);near(edge.area_factor/e.patches()[edge.first].area,edge.area_factor/e.patches()[edge.second].area); }
      require(e.page(0,1).size()==1);rejects([&]{e.page(0,4097);});rejects([&]{e.page(2,1);});
      auto rows=e.raw();rows[0].escaped++;rejects([&]{Exchange x(e.patches(),rows);});rows=e.raw();rows[1].source=0;rejects([&]{Exchange x(e.patches(),rows);});
      auto closed=trace(Mesh(cube()),{1701,16384,100});for(double v:closed.escape())near(v,0);
      std::vector<double> totals(closed.patches().size());for(const auto& edge:closed.edges()){totals[edge.first]+=edge.area_factor;if(edge.first!=edge.second)totals[edge.second]+=edge.area_factor;}
      for(double v:totals)near(v,1,2e-12);
    } else if(name=="black-gray-sphere") {
      constexpr double s=5.670374419e-8;std::vector<double> t{400,300};
      auto black=evaluate(exact_pair(),t);double q=s*(std::pow(400.,4)-std::pow(300.,4));near(black.internal_power[0],-q);near(sum(black.internal_power),0);near(sum(black.environment),0);
      auto gray=evaluate(exact_pair(1,1,1,1,{.4,.7,true},{.8,.5,true}),t);near(gray.internal_power[0],-q/(1/.7+1/.5-1),1e-10);
      Exchange sphere({{"a","a","main",0,false,1,{.4,.7,true}},{"b","b","main",1,false,4,{.8,.5,true}}},
        {{0,100,0,0,{{1,100}}},{1,100,0,0,{{0,25},{1,75}}}});
      auto value=evaluate(sphere,t);near(value.internal_power[0],-q/(1/.7+.25*(1/.5-1)),1e-10);near(sum(value.internal_power),0);
      auto env=evaluate(exact_pair(1,1,0,0,{.2,.7,true},{.8,.5,true}),t,{200,1e-12,100000,{100,100}});
      near(env.environment[0],.7*s*(std::pow(200.,4)-std::pow(400.,4))+20);near(env.environment[1],.5*s*(std::pow(200.,4)-std::pow(300.,4))+80);
      auto solar=evaluate(exact_pair(1,1,1,1,{.2,.7,true},{.8,.5,true}),t,{0,1e-12,100000,{100,0}});near(sum(solar.environment),100,1e-10);
    } else if(name=="jacobian") {
      auto e=std::make_shared<const Exchange>(exact_pair(1,2,.5,.25,{.3,.7,true},{.8,.4,true}));
      auto bindings=bind(e,uid(22),uid(14),{150,1e-12,100000,{100,20}});std::vector<double> t{350,300};
      for(const auto& b:bindings) {
        auto analytic=b.evaluate(0,t,true);
        for(std::size_t k=0;k<b.dependencies.size();++k) {
          auto entry=b.dependencies[k];auto plus=t,minus=t;plus[entry.column]+=.001;minus[entry.column]-=.001;
          auto a=b.evaluate(0,plus,false),c=b.evaluate(0,minus,false);near(analytic.d_temperature[k],(a.watts[entry.row]-c.watts[entry.row])/.002,1e-7);
        }
      }
    } else if(name=="thermal-coupling") {
      auto m=model(root);auto e=std::make_shared<const Exchange>(exact_pair(1,1,.2,.2,{.3,.7,true},{.8,.4,true}));
      auto ps=bind(e,uid(22),uid(14),{300,1e-13,100000,{}});thermal::Assembly a(m,ps);
      auto steady=thermal::solve_steady(a);require(steady.solve.status==thermal::SolveStatus::converged && steady.balance);
      near(steady.balance->energy_defect,0,1e-7);near(sum(steady.balance->radiation_in),0);
      auto linear=a.steady_linearize(0,std::vector<double>{320,310});
      for(std::size_t j=0;j<2;++j){std::vector<double> plus{320,310},minus=plus;plus[j]+=.001;minus[j]-=.001;auto p=a.steady_residual(0,plus),n=a.steady_residual(0,minus);for(std::size_t i=0;i<2;++i)near(linear.d_temperature.at({i,j}),(p.residual[i]-n.residual[i])/.002,1e-7);}
      thermal::TransientOptions o;o.end=.1;o.output_times={0,.1};o.callback_revision=std::string(64,'a');
      auto transient=thermal::solve_transient(a,o);require(transient.valid);require(transient.samples.back().valid);
      near(transient.samples.back().balance.internal_exchange_defect,0,1e-7);near(transient.samples.back().run_energy.defect,0,1e-6);
    } else if(name=="limits-failures") {
      auto e=exact_pair();std::vector<double> t{300,300};rejects([&]{evaluate(e,std::vector<double>{300});});rejects([&]{evaluate(e,std::vector<double>{-1,300});});
      rejects([&]{evaluate(e,t,{0,0,100,{}});});rejects([&]{evaluate(e,t,{0,1e-12,100,{1}});});
      auto gray=exact_pair(1,1,1,1,{.4,.1,true},{.8,.1,true});rejects([&]{evaluate(gray,std::vector<double>{400,300},{0,1e-12,1,{}});});
      auto mirror=exact_pair(1,1,1,1,{0,0,true},{0,0,true});rejects([&]{evaluate(mirror,t);});
      rejects([&]{bind(std::make_shared<const Exchange>(e),uid(22),uid(14),{},3);});
      rejects([&]{trace(Mesh(cube()),{1701,100,1});});
      auto restricted=exact_pair();auto p=restricted.patches();p[0].optics.dataset.maximum_temperature=200;
      Exchange domain(p,restricted.raw());rejects([&]{evaluate(domain,t);});
      auto mirror_solar=exact_pair(1,1,1,1,{0,.5,true},{0,.7,true});rejects([&]{evaluate(mirror_solar,t,{0,1e-12,100,{100,0}});});
    } else if(name=="sparse-storage") {
      std::vector<Patch> patches;std::vector<Row> rows;std::vector<double> t(10000,300);
      for(std::size_t i=0;i<t.size();++i) { auto id="patch-"+std::to_string(i);patches.push_back({id,id,"main",i,false,1,{}});rows.push_back({i,1,1,0,{}}); }
      Exchange e(std::move(patches),std::move(rows));require(e.edges().empty());auto result=evaluate(e,t,{300,1e-12,100,{}});
      near(sum(result.internal_power),0);near(sum(result.environment),0);require(result.iterations<=2);
      auto corrected=trace(Mesh(spheres()),{1701,65536,100});
      require(corrected.diagnostics().maximum_correction<.01);
      for(const auto& edge:corrected.edges()) if(edge.first!=edge.second) near(edge.area_factor/corrected.patches()[edge.first].area,1,.01);
    } else throw std::runtime_error("unknown_case");
    std::cout<<"passed\n";return 0;
  } catch(const thermal::Error& e) { std::cerr<<e.code<<'\n';return 1; }
    catch(const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
