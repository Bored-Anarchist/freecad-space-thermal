// SPDX-License-Identifier: MIT OR Apache-2.0
// Native execution JSON adapter. Included where the bounded owned JSON codec lives.
namespace {
void execution_keys(const J& j,std::initializer_list<const char*> required,std::initializer_list<const char*> optional={}) {
  if(!j.isobj())fail("schema"); std::set<std::string> allowed;
  for(auto key:required) {if(!j.has(key))fail("schema");allowed.insert(key);}
  for(auto key:optional)allowed.insert(key);
  for(const auto& [key,value]:j.obj()) { (void)value; if(!allowed.contains(key))fail("schema"); }
}
J numbers(std::span<const double> values) { J::A out;for(double v:values)out.emplace_back(v);return J(out); }
std::vector<double> execution_numbers(const J& j) { std::vector<double> out;for(const auto& v:j.arr())out.push_back(v.num());return out; }
std::size_t execution_count(const J& j) { double n=j.num();if(n<0 || n>10000000 || n!=std::floor(n))fail("range");return static_cast<std::size_t>(n); }
J state_json(const thermal::OperatingState& s) {
  J::O heaters,factors;for(const auto& [id,on]:s.heaters)heaters.emplace(id,J(on));for(const auto& [id,f]:s.load_factors)factors.emplace(id,J(f));
  return J(J::O{{"heaters",J(heaters)},{"load_factors",J(factors)}});
}
thermal::OperatingState execution_state(const J& j) {
  execution_keys(j,{"heaters","load_factors"});thermal::OperatingState s;
  for(const auto& [id,v]:j.at("heaters").obj())s.heaters.emplace(id,std::get<bool>(v.v));
  for(const auto& [id,v]:j.at("load_factors").obj())s.load_factors.emplace(id,v.num());return s;
}
J budget_json(const thermal::EnergyBudget& b) {
  return J(J::O{{"storage_change_J",numbers(b.storage_change)},{"external_energy_J",numbers(b.external_energy)},
    {"conductive_energy_J",numbers(b.conductive_energy)},{"boundary_energy_J",numbers(b.boundary_energy)},
    {"defect_J",J(b.defect)},{"absolute_exchange_J",J(b.absolute_exchange)}});
}
thermal::EnergyBudget execution_budget(const J& j) {
  execution_keys(j,{"storage_change_J","external_energy_J","conductive_energy_J","boundary_energy_J","defect_J","absolute_exchange_J"});
  return {execution_numbers(j.at("storage_change_J")),execution_numbers(j.at("external_energy_J")),
    execution_numbers(j.at("conductive_energy_J")),execution_numbers(j.at("boundary_energy_J")),j.at("defect_J").num(),j.at("absolute_exchange_J").num()};
}
J checkpoint_json(const thermal::TransientCheckpoint& c) {
  J::O last,on;for(const auto& [id,t]:c.last_switch)last.emplace(id,J(t));for(const auto& [id,t]:c.on_seconds)on.emplace(id,J(t));
  return J(J::O{{"version",J(static_cast<double>(c.version))},{"configuration_id",J(c.configuration_id)},{"checksum",J(c.checksum)},
    {"time",J(c.time)},{"origin",J(c.origin)},{"next_step",J(c.next_step)},{"temperature",numbers(c.temperature)},
    {"initial_temperature",numbers(c.initial_temperature)},{"operating",state_json(c.operating)},{"last_switch",J(last)},{"on_seconds",J(on)},
    {"run_energy",budget_json(c.run_energy)},{"accepted_steps",J(static_cast<double>(c.accepted_steps))},
    {"rejected_steps",J(static_cast<double>(c.rejected_steps))},{"event_count",J(static_cast<double>(c.event_count))}});
}
thermal::TransientCheckpoint execution_checkpoint(const J& j) {
  execution_keys(j,{"version","configuration_id","checksum","time","origin","next_step","temperature","initial_temperature",
    "operating","last_switch","on_seconds","run_energy","accepted_steps","rejected_steps","event_count"});
  thermal::TransientCheckpoint c;c.version=static_cast<unsigned>(execution_count(j.at("version")));c.configuration_id=j.at("configuration_id").str();
  c.checksum=j.at("checksum").str();c.time=j.at("time").num();c.origin=j.at("origin").num();c.next_step=j.at("next_step").num();
  c.temperature=execution_numbers(j.at("temperature"));c.initial_temperature=execution_numbers(j.at("initial_temperature"));c.operating=execution_state(j.at("operating"));
  for(const auto& [id,t]:j.at("last_switch").obj())c.last_switch.emplace(id,t.num());for(const auto& [id,t]:j.at("on_seconds").obj())c.on_seconds.emplace(id,t.num());
  c.run_energy=execution_budget(j.at("run_energy"));c.accepted_steps=execution_count(j.at("accepted_steps"));c.rejected_steps=execution_count(j.at("rejected_steps"));c.event_count=execution_count(j.at("event_count"));return c;
}
J capabilities_json() {
  auto c=thermal::thermal_backend_capabilities();
  return J(J::O{{"execution_mode",J(c.execution_mode)},{"linear",J(c.linear)},{"nonlinear",J(c.nonlinear)},{"transient",J(c.transient)},
    {"source_revision",J(c.source_revision)},{"compiler",J(c.compiler)},{"compiler_version",J(c.compiler_version)},
    {"stiff",J(c.stiff)},{"index_one_dae",J(c.index_one_dae)},{"enthalpy",J(c.enthalpy)},{"events",J(c.events)},{"checkpoint",J(c.checkpoint)},
    {"external_reference",J(c.external_reference)},{"durable_job_solver",J(c.durable_job_solver)}});
}
}
std::string thermal::inspect_thermal_capabilities() { return dump(J(J::O{{"status",J("passed")},{"backend",capabilities_json()}})); }
std::string thermal::inspect_transient(std::string_view input) {
  try {
    auto j=Parser{input}.parse();execution_keys(j,{"thermal_input","transient"},{"checkpoint","initial_operating","environment_power_W"});
    auto model=thermal::load(dump(j.at("thermal_input")));auto state=initial_operating_state(model);
    if(j.has("initial_operating"))state=execution_state(j.at("initial_operating"));
    const auto& settings=j.at("transient");execution_keys(settings,{"start","end","output_times"},
      {"initial_step","minimum_step","maximum_step","absolute_temperature_tolerance","relative_temperature_tolerance",
       "absolute_energy_tolerance","relative_energy_tolerance","event_time_tolerance","minimum_event_separation",
       "maximum_attempts","maximum_events","maximum_newton_iterations","temperature_tolerances","schedules","maximum_result_values","include_steps"});
    TransientOptions o;o.start=settings.at("start").num();o.end=settings.at("end").num();o.output_times=execution_numbers(settings.at("output_times"));
    for(auto [key,target]:std::initializer_list<std::pair<const char*,double*>>{
      {"initial_step",&o.initial_step},{"minimum_step",&o.minimum_step},{"maximum_step",&o.maximum_step},
      {"absolute_temperature_tolerance",&o.absolute_temperature_tolerance},{"relative_temperature_tolerance",&o.relative_temperature_tolerance},
      {"absolute_energy_tolerance",&o.absolute_energy_tolerance},{"relative_energy_tolerance",&o.relative_energy_tolerance},
      {"event_time_tolerance",&o.event_time_tolerance},{"minimum_event_separation",&o.minimum_event_separation}}) if(settings.has(key))*target=settings.at(key).num();
    for(auto [key,target]:std::initializer_list<std::pair<const char*,std::size_t*>>{
      {"maximum_attempts",&o.maximum_attempts},{"maximum_events",&o.maximum_events},{"maximum_newton_iterations",&o.maximum_newton_iterations},
      {"maximum_result_values",&o.maximum_result_values}})if(settings.has(key))*target=execution_count(settings.at(key));
    if(settings.has("temperature_tolerances"))o.temperature_tolerances=execution_numbers(settings.at("temperature_tolerances"));
    if(settings.has("schedules"))for(const auto& s:settings.at("schedules").arr()) {
      execution_keys(s,{"load_id","points"});LoadSchedule schedule;schedule.load_id=s.at("load_id").str();
      for(const auto& p:s.at("points").arr()) {execution_keys(p,{"time","factor"});schedule.points.push_back({p.at("time").num(),p.at("factor").num()});}o.schedules.push_back(std::move(schedule));
    }
    std::vector<PowerBinding> powers;
    if(j.has("environment_power_W"))for(const auto& [id,power]:j.at("environment_power_W").obj()) {
      auto watts=execution_numbers(power);if(watts.size()!=model.data().nodes.size())fail("dimension");
      std::vector<std::size_t> nodes;for(std::size_t i=0;i<watts.size();++i)nodes.push_back(i);
      powers.push_back({id,PowerKind::environment,nodes,{},[watts](double,std::span<const double>,bool){return PowerEvaluation{watts,{}};}});
    }
    if(!powers.empty())o.callback_revision=thermal_digest(canonical(j.at("environment_power_W")));
    Assembly assembly(std::move(model),std::move(powers),{},state);std::optional<TransientCheckpoint> restart;
    if(j.has("checkpoint"))restart=execution_checkpoint(j.at("checkpoint"));auto result=solve_transient(assembly,o,restart);
    J::A samples,steps,events,node_ids,equation_ids,conductor_ids;
    for(const auto& node:assembly.model().data().nodes) {node_ids.emplace_back(node.id);if(node.equation)equation_ids.emplace_back(node.id);}
    for(const auto& conductor:assembly.model().data().conductors)conductor_ids.emplace_back(conductor.id);
    for(const auto& s:result.samples) {
      J::O duty;for(const auto& [id,v]:s.duty_cycles)duty.emplace(id,J(v));
      samples.emplace_back(J::O{{"time_s",J(s.time)},{"valid",J(s.valid)},{"temperature_K",numbers(s.balance.temperature)},
        {"conductive_in_W",numbers(s.balance.conductive_in)},{"conductor_power_W",numbers(s.balance.conductor_power)},
        {"boundary_power_W",numbers(s.balance.boundary_power)},{"load_in_W",numbers(s.balance.load_in)},
        {"radiation_in_W",numbers(s.balance.radiation_in)},{"environment_in_W",numbers(s.balance.environment_in)},
        {"storage_power_W",numbers(s.balance.storage_power)},{"residual_W",numbers(s.balance.residual)},
        {"rate_K_per_s",numbers(s.rate)},{"storage_change_J",numbers(s.storage_change)},
        {"operating",state_json(s.operating)},{"duty_cycles",J(duty)},{"run_energy",budget_json(s.run_energy)}});
    }
    const bool include_steps=!settings.has("include_steps") || std::get<bool>(settings.at("include_steps").v);
    if(include_steps)for(const auto& s:result.steps)steps.emplace_back(J::O{{"start_s",J(s.start)},{"end_s",J(s.end)},{"error_norm",J(s.error_norm)},
      {"accepted",J(s.accepted)},{"reason",J(s.reason)},{"energy",budget_json(s.energy)}});
    for(const auto& e:result.events)events.emplace_back(J::O{{"time_s",J(e.time)},{"entity_id",J(e.entity_id)},
      {"kind",J(e.kind)},{"before",J(e.before)},{"after",J(e.after)}});
    const auto& p=result.profile;
    J::O out{{"status",J(result.valid?"passed":"failed")},{"valid",J(result.valid)},{"reason",J(result.reason)},
      {"model_hash",J(result.model_hash)},{"preparation_hash",J(result.preparation_hash)},{"configuration_id",J(result.configuration_id)},
      {"backend",capabilities_json()},{"node_ids",J(node_ids)},{"equation_node_ids",J(equation_ids)},{"conductor_ids",J(conductor_ids)},
      {"samples",J(samples)},{"steps",J(steps)},{"step_records_included",J(include_steps)},
      {"step_count",J(static_cast<double>(result.steps.size()))},{"events",J(events)},
      {"checkpoint",result.checkpoint?checkpoint_json(*result.checkpoint):J()},
      {"profile",J(J::O{{"residual_evaluations",J(static_cast<double>(p.residual_evaluations))},{"jacobian_evaluations",J(static_cast<double>(p.jacobian_evaluations))},
        {"linear_solves",J(static_cast<double>(p.linear_solves))},{"newton_iterations",J(static_cast<double>(p.newton_iterations))},
        {"event_probes",J(static_cast<double>(p.event_probes))},{"assembly_seconds",J(p.assembly_seconds)},
        {"linear_seconds",J(p.linear_seconds)},{"total_seconds",J(p.total_seconds)}})}};
    if(!result.entity_id.empty())out.emplace("entity_id",J(result.entity_id));if(!result.source_map_id.empty())out.emplace("source_map_id",J(result.source_map_id));
    return dump(J(out));
  } catch(const thermal::Error& e) {
    J::O out{{"status",J("failed")},{"code",J(e.code)}};
    if(e.entity_id.size()==36 && std::regex_match(e.entity_id,std::regex("[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")))
      out.emplace("entity_id",J(e.entity_id));
    return dump(J(out));
  }
    catch(const fcst::Error& e) {return dump(J(J::O{{"status",J("failed")},{"code",J(e.code)}}));}
    catch(...) {return "{\"status\":\"failed\",\"code\":\"schema\"}";}
}
