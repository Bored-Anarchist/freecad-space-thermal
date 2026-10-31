// SPDX-License-Identifier: MIT OR Apache-2.0
// Included inside namespace fcst, using the shared bounded strict JSON parser.
std::string radiation::inspect(std::string_view input,bool steady) {
  try {
    if(input.size()>1048576) fail("input_limit");
    auto value=Parser{input}.parse();
    auto fields=[](const J& object,std::initializer_list<std::string_view> allowed) {
      if(!object.isobj()) fail("schema");
      for(const auto& [key,v]:object.obj()) { (void)v; if(std::find(allowed.begin(),allowed.end(),key)==allowed.end()) fail("schema"); }
    };
    auto number=[](const J& v) { if(!v.isnum() || !std::isfinite(v.num())) fail("schema"); return v.num(); };
    auto integer=[&](const J& v) { auto x=number(v); if(x<0 || x>1000000000 || x!=std::floor(x)) fail("schema"); return static_cast<std::uint64_t>(x); };
    auto text=[](const J& v) { if(!v.isstr() || v.str().empty() || v.str().size()>256) fail("schema"); return v.str(); };
    auto array=[](const J& v)->const J::A& { if(!v.isarr()) fail("schema"); return v.arr(); };
    auto optical=[&](const J& v) {
      fields(v,{"solar_absorptance","ir_emittance","active","dataset"});
      if(!std::holds_alternative<bool>(v.at("active").v)) fail("schema");
      radiation::Optics o{number(v.at("solar_absorptance")),number(v.at("ir_emittance")),std::get<bool>(v.at("active").v)};
      const auto& d=v.at("dataset"); fields(d,{"solar_band","infrared_band","valid_temperature_K","condition","absolute_uncertainty","provenance"});
      o.dataset.solar_band=text(d.at("solar_band"));o.dataset.infrared_band=text(d.at("infrared_band"));
      const auto& range=array(d.at("valid_temperature_K"));const auto& uncertainty=array(d.at("absolute_uncertainty"));
      if(range.size()!=2 || uncertainty.size()!=2) fail("schema");
      o.dataset.minimum_temperature=number(range[0]);o.dataset.maximum_temperature=number(range[1]);
      o.dataset.absolute_uncertainty={number(uncertainty[0]),number(uncertainty[1])};
      o.dataset.condition=text(d.at("condition"));o.dataset.provenance=text(d.at("provenance"));return o;
    };
    fields(value,{"schema_version","facets","excluded_facets","sampling","temperatures_K","environment","thermal_input"});
    if(integer(value.at("schema_version"))!=1) fail("version");
    std::vector<radiation::Facet> facets;
    for(const auto& f:array(value.at("facets"))) {
      fields(f,{"id","surface_id","group","node","vertices_m","front","back"});
      radiation::Facet facet; facet.id=text(f.at("id")); facet.surface_id=text(f.at("surface_id")); facet.group=text(f.at("group"));
      facet.node=static_cast<std::size_t>(integer(f.at("node"))); facet.front=optical(f.at("front")); facet.back=optical(f.at("back"));
      const auto& vertices=array(f.at("vertices_m")); if(vertices.size()!=3) fail("schema");
      for(std::size_t i=0;i<3;++i) { const auto& xyz=array(vertices[i]); if(xyz.size()!=3) fail("schema"); for(std::size_t k=0;k<3;++k) facet.vertices[i][k]=number(xyz[k]); }
      facets.push_back(std::move(facet));
    }
    std::vector<std::string> excluded;
    if(value.has("excluded_facets")) for(const auto& id:array(value.at("excluded_facets"))) excluded.push_back(text(id));
    radiation::Sampling sampling;
    sampling.maximum_entries=4096;
    fields(value.at("sampling"),{"seed","samples","maximum_entries"});
    sampling.seed=integer(value.at("sampling").at("seed")); sampling.samples=integer(value.at("sampling").at("samples"));
    if(value.at("sampling").has("maximum_entries")) sampling.maximum_entries=static_cast<std::size_t>(integer(value.at("sampling").at("maximum_entries")));
    if(sampling.maximum_entries>4096 || sampling.samples>1000000 || facets.size()>4096) fail("radiation_limit");
    radiation::RadiosityOptions options;
    fields(value.at("environment"),{"temperature_K","solar_incident_W_m2"});
    options.background_temperature=number(value.at("environment").at("temperature_K"));
    if(value.at("environment").has("solar_incident_W_m2")) for(const auto& v:array(value.at("environment").at("solar_incident_W_m2"))) options.solar_incident.push_back(number(v));
    radiation::Mesh mesh(std::move(facets),std::move(excluded));
    auto exchange=std::make_shared<const radiation::Exchange>(radiation::trace(mesh,sampling));
    std::vector<double> temperatures;
    if(value.has("temperatures_K")) for(const auto& t:array(value.at("temperatures_K"))) temperatures.push_back(number(t));
    J::O out{{"status",J("passed")},{"execution_mode",J("fcst_native")},{"schema_version",J(1.0)},
      {"seed",J(static_cast<double>(sampling.seed))},{"samples_per_patch",J(static_cast<double>(sampling.samples))}};
    if(steady) {
      if(!value.has("thermal_input") || value.has("temperatures_K")) fail("schema");
      auto model=thermal::load(dump(value.at("thermal_input"))); const auto& d=model.data();
      if(d.radiation.size()!=1 || d.active_environment_ids.size()!=1 || d.radiation[0].environment_id!=d.active_environment_ids[0] || d.radiation[0].method!="diffuse") fail("radiation_mapping");
      std::set<std::string> expected(d.radiation[0].facet_ids.begin(),d.radiation[0].facet_ids.end()),actual;
      for(const auto& f:mesh.facets()) { actual.insert(f.id); if(f.node>=d.nodes.size()) fail("radiation_mapping"); }
      for(const auto& id:d.radiation[0].excluded_facet_ids) expected.erase(id);
      if(actual!=expected || !options.solar_incident.empty()) fail("radiation_mapping");
      if(d.case_id) fail("radiation_case_not_supported");
      auto canonical=Parser{d.canonical_snapshot}.parse(); Entities entities;
      for(const auto& entity:canonical.at("entities").arr()) entities.emplace(entity.at("id").str(),entity);
      for(const auto& f:mesh.facets()) {
        const auto& declared=entities.at(f.id);
        const auto& declared_optics=entities.at(declared.at("optics_id").str());
        const bool back=declared.at("side").str()=="back"; const auto& assigned=back?f.back:f.front;
        if(!assigned.active || (back?f.front.active:f.back.active) ||
           declared_optics.at("specular_fraction").num()!=0 || declared_optics.at("transmissivity").num()!=0 ||
           assigned.solar_absorptance!=declared_optics.at("solar_absorptivity").num() || assigned.ir_emittance!=declared_optics.at("ir_emissivity").num()) fail("radiation_mapping");
        const auto& a=f.vertices[0];const auto& b=f.vertices[1];const auto& c=f.vertices[2];
        std::array<double,3> u{b[0]-a[0],b[1]-a[1],b[2]-a[2]},v{c[0]-a[0],c[1]-a[1],c[2]-a[2]};
        double area=.5*std::hypot(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]);
        double expected_area=declared.at("area").at("value").num();
        if(std::abs(area-expected_area)>1e-10*expected_area) fail("radiation_mapping");
      }
      auto env=std::find_if(d.environments.begin(),d.environments.end(),[&](const auto& e) { return e.id==d.active_environment_ids[0]; });
      if(env==d.environments.end() || options.background_temperature!=env->background_temperature || env->solar_flux!=0) fail("radiation_mapping");
      auto powers=radiation::bind(exchange,d.radiation[0].id,d.active_environment_ids[0],options);
      thermal::Assembly assembly(std::move(model),std::move(powers)); auto result=thermal::solve_steady(assembly);
      if(result.solve.status!=thermal::SolveStatus::converged || !result.balance) throw thermal::Error("radiation_steady_failed");
      temperatures=result.balance->temperature;
      out.emplace("energy_defect_W",J(result.balance->energy_defect));
      out.emplace("model_hash",J(assembly.model().data().model_hash));
    } else if(value.has("thermal_input") || temperatures.empty()) fail("schema");
    auto evaluated=radiation::evaluate(*exchange,temperatures,options);
    J::A patches,raw,edges,ts;
    for(double t:temperatures) ts.emplace_back(t);
    for(std::size_t i=0;i<exchange->patches().size();++i) {
      const auto& p=exchange->patches()[i];
      patches.emplace_back(J::O{{"id",J(p.id)},{"surface_id",J(p.surface_id)},{"node",J(static_cast<double>(p.node))},{"back",J(p.back)},
        {"area_m2",J(p.area)},{"escape",J(exchange->escape()[i])},{"radiosity_W_m2",J(evaluated.radiosity[i])},
        {"internal_W",J(evaluated.internal_power[i])},{"environment_W",J(evaluated.environment[i])},
        {"optical_dataset",J(J::O{{"solar_band",J(p.optics.dataset.solar_band)},{"infrared_band",J(p.optics.dataset.infrared_band)},
          {"valid_temperature_K",J(J::A{J(p.optics.dataset.minimum_temperature),J(p.optics.dataset.maximum_temperature)})},
          {"condition",J(p.optics.dataset.condition)},{"provenance",J(p.optics.dataset.provenance)},
          {"absolute_uncertainty",J(J::A{J(p.optics.dataset.absolute_uncertainty[0]),J(p.optics.dataset.absolute_uncertainty[1])})}})}});
      const auto& r=exchange->raw()[i]; J::A counts;
      for(const auto& c:r.counts) counts.emplace_back(J::O{{"target",J(static_cast<double>(c.target))},{"hits",J(static_cast<double>(c.hits))}});
      raw.emplace_back(J::O{{"source",J(static_cast<double>(i))},{"samples",J(static_cast<double>(r.samples))},
        {"escaped",J(static_cast<double>(r.escaped))},{"blocked",J(static_cast<double>(r.blocked))},{"counts",J(counts)}});
    }
    // Bounded first page; the native Exchange API supports subsequent pages.
    for(const auto& e:exchange->page(0,std::min<std::size_t>(4096,exchange->edges().size()))) edges.emplace_back(J::O{
      {"first",J(static_cast<double>(e.first))},{"second",J(static_cast<double>(e.second))},{"area_factor_m2",J(e.area_factor)}});
    const auto& diagnostics=exchange->diagnostics();
    out.emplace("patches",J(patches)); out.emplace("raw",J(raw)); out.emplace("edges",J(edges)); out.emplace("temperatures_K",J(ts));
    out.emplace("edge_count",J(static_cast<double>(exchange->edges().size())));
    out.emplace("maximum_raw_reciprocity",J(diagnostics.maximum_raw_reciprocity)); out.emplace("maximum_correction",J(diagnostics.maximum_correction));
    out.emplace("linear_defect_W_m2",J(evaluated.linear_defect));
    return dump(J(out));
  } catch(const thermal::Error& e) { return dump(J(J::O{{"status",J("failed")},{"code",J(e.code)}})); }
    catch(const Error& e) { return dump(J(J::O{{"status",J("failed")},{"code",J(e.code)}})); }
    catch(...) { return "{\"status\":\"failed\",\"code\":\"radiation_schema\"}"; }
}
