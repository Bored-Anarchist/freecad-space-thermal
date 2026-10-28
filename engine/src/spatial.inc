// SPDX-License-Identifier: MIT OR Apache-2.0
// Independent spatial reader, using only the JSON/schema primitives in contracts.cpp.
double spatial_det(const J& m) {
  auto a=[&](std::size_t i,std::size_t k){return m.at(i).at(k).num();};
  return a(0,0)*(a(1,1)*a(2,2)-a(1,2)*a(2,1))-a(0,1)*(a(1,0)*a(2,2)-a(1,2)*a(2,0))+a(0,2)*(a(1,0)*a(2,1)-a(1,1)*a(2,0));
}
void check_spatial(const J& j) {
  const auto& vertices=j.at("vertices"); const auto& ids=j.at("vertex_ids");
  if(vertices.arr().size()!=ids.arr().size()) fail("spatial_shape");
  std::set<std::string> all; std::map<std::string,J> frames;
  std::map<std::string,std::set<std::string>> domains;
  auto add=[&](const J& id,const std::string& domain){if(!all.insert(id.str()).second) fail("spatial_identity"); domains[domain].insert(id.str());};
  for(const auto& id:ids.arr()) add(id,"mesh_vertex");
  for(const auto& c:j.at("cells").arr()) add(c.at("id"),c.at("topology").str()=="tet4"?"element":"facet");
  for(const auto& f:j.at("frames").arr()) {add(f.at("id"),"frame"); frames.emplace(f.at("id").str(),f.at("basis"));}
  for(const auto& id:j.at("cad_face_ids").arr()) add(id,"cad_face");
  for(const auto& id:j.at("thermal_node_ids").arr()) add(id,"thermal_node");
  for(const auto& [id,m]:frames) {
    (void)id;
    if(std::abs(spatial_det(m)-1)>1e-12) fail("spatial_frame");
    for(std::size_t i=0;i<3;++i) for(std::size_t k=0;k<3;++k) {double dot=0; for(std::size_t r=0;r<3;++r) dot+=m.at(r).at(i).num()*m.at(r).at(k).num(); if(std::abs(dot-(i==k?1:0))>1e-12) fail("spatial_frame");}
  }
  for(const auto& cell:j.at("cells").arr()) {
    bool tet=cell.at("topology").str()=="tet4"; const auto& indices=cell.at("vertices").arr();
    if(indices.size()!=(tet?4u:3u)) fail("spatial_connectivity");
    for(const auto& index:indices) if(index.num()>=static_cast<double>(ids.arr().size())) fail("spatial_connectivity");
    J::A edges; const auto& origin=vertices.at(static_cast<std::size_t>(indices[0].num()));
    for(std::size_t i=1;i<indices.size();++i) {J::A edge; for(std::size_t k=0;k<3;++k) edge.emplace_back(vertices.at(static_cast<std::size_t>(indices[i].num())).at(k).num()-origin.at(k).num()); edges.emplace_back(edge);}
    bool valid;
    if(tet) valid=spatial_det(J(edges))>1e-18;
    else {double norm=0; for(std::size_t k=0;k<3;++k) {auto x=edges[0].at((k+1)%3).num()*edges[1].at((k+2)%3).num()-edges[0].at((k+2)%3).num()*edges[1].at((k+1)%3).num(); norm+=x*x;} valid=norm>1e-24;}
    if(!valid) fail("spatial_orientation");
  }
  J mesh(J::O{{"vertex_ids",ids},{"vertices",vertices},{"cells",j.at("cells")}});
  if(j.at("mesh_revision").str()!=sha256(std::string("FCST-mesh-v2\0",13)+canonical(mesh))) fail("spatial_mesh_revision");
  const auto& material=j.at("material"); const auto& m=material.at("conductivity");
  if(!frames.contains(material.at("frame_id").str())) fail("spatial_reference");
  for(std::size_t i=0;i<3;++i) for(std::size_t k=0;k<3;++k) if(std::abs(m.at(i).at(k).num()-m.at(k).at(i).num())>1e-12) fail("spatial_material");
  if(m.at(0).at(0).num()<=0 || m.at(0).at(0).num()*m.at(1).at(1).num()-std::pow(m.at(0).at(1).num(),2)<=0 || spatial_det(m)<=0) fail("spatial_material");
  const auto& times=j.at("times").arr(); for(std::size_t i=1;i<times.size();++i) if(times[i-1].num()>=times[i].num()) fail("spatial_time");
  std::set<std::string> quantities;
  for(const auto& f:j.at("fields").arr()) {
    if(!quantities.insert(f.at("quantity").str()).second) fail("spatial_identity");
    if(f.at("entity_ids")!=ids || !frames.contains(f.at("frame_id").str())) fail("spatial_reference");
    if(f.at("values").arr().size()!=times.size()) fail("spatial_shape");
    for(const auto& row:f.at("values").arr()) {
      if(row.arr().size()!=ids.arr().size()) fail("spatial_shape");
      if(f.at("quantity").str()=="temperature") for(const auto& x:row.arr()) if(x.at(0).num()<0) fail("spatial_range");
    }
  }
  std::vector<J> maps=j.at("mappings").arr(); std::sort(maps.begin(),maps.end(),[](const J& a,const J& b){return std::pair{a.at("from_id").str(),a.at("to_id").str()}<std::pair{b.at("from_id").str(),b.at("to_id").str()};});
  std::map<std::pair<std::string,std::string>,double> weights; std::set<std::pair<std::string,std::string>> pairs;
  const std::set<std::pair<std::string,std::string>> allowed{{"cad_face","facet"},{"cad_face","element"},{"facet","thermal_node"},{"element","thermal_node"},{"mesh_vertex","thermal_node"}};
  for(const auto& map:maps) {
    auto a=map.at("from_kind").str(),b=map.at("to_kind").str(),from=map.at("from_id").str(),to=map.at("to_id").str();
    if(!allowed.contains({a,b}) || !domains[a].contains(from) || !domains[b].contains(to)) fail("spatial_reference");
    if(!pairs.insert({from,to}).second) fail("spatial_identity"); weights[{from,b}]+=map.at("weight").num();
  }
  for(const auto& [key,w]:weights) {(void)key; if(std::abs(w-1)>1e-12) fail("spatial_weight");}
  const auto& boundary=j.at("boundary"); auto kind=boundary.at("kind").str();
  std::map<std::string,std::string> units{{"none","1"},{"surface_flux","W/m2"},{"total_power","W"},{"prescribed_temperature","K"}};
  if(boundary.at("unit").str()!=units.at(kind) || (kind=="prescribed_temperature" && boundary.at("value").num()<0)) fail("spatial_boundary");
  const auto& cells=boundary.at("cell_ids").arr();
  if((kind=="none" && (!cells.empty() || boundary.at("value").num()!=0)) || (kind!="none" && cells.empty())) fail("spatial_reference");
  for(const auto& cell:cells) if(!domains["facet"].contains(cell.str())) fail("spatial_reference");
}
