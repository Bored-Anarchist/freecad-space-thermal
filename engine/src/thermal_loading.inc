// SPDX-License-Identifier: MIT OR Apache-2.0
// JSON adapter only. Reuses the bounded native parser, validator and SI reader.
thermal::PropertyLaw thermal_law(const J& table, const std::string& dimension_name, double lo, double hi) {
  std::vector<double> x, y;
  std::vector<std::size_t> jumps;
  for (const auto& q : table.at("temperature").arr()) x.push_back(quantity(q, "temperature", 0));
  for (const auto& q : table.at("values").arr()) y.push_back(quantity(q, dimension_name, 0, true));
  for (const auto& i : table.at("discontinuities").arr()) jumps.push_back(static_cast<std::size_t>(i.num()));
  return {std::move(x), std::move(y),
      table.at("interpolation").str() == "linear" ? thermal::Interpolation::linear : thermal::Interpolation::previous,
      table.at("extrapolation").str() == "error" ? thermal::Extrapolation::error : thermal::Extrapolation::clamp,
      std::move(jumps), lo, hi};
}
thermal::Data thermal_data(std::string_view input) {
  auto envelope = Parser{input}.parse();
  if (!envelope.has("contract_version") || envelope.at("contract_version") != J("1.0.0")) fail("version");
  static const J schema = [] {
    std::string bytes;
    for (auto part : thermal_input_schema_parts) bytes += part;
    return Parser{bytes}.parse();
  }();
  validate(schema, envelope, schema);
  // Validate the original nested model separately so its source-aware errors survive.
  auto model = read("model", envelope.at("model"));
  try {
    envelope = normalize(envelope);
    envelope.at("model") = model;
    thermal::Data out;
    out.project_id = model.at("project_id").str();
    auto frozen = snapshot(model);
    out.canonical_snapshot = dump(frozen);
    out.model_hash = sha256(std::string("FCST-semantic-v1\0",17) + canonical(frozen));
    Entities entities;
    for (const auto& e : model.at("entities").arr()) entities.emplace(e.at("id").str(), e);
    if (envelope.has("case_id")) {
      out.case_id = envelope.at("case_id").str();
      const auto& selected = target(entities, *out.case_id, "case");
      std::set<std::pair<std::string, std::string>> seen;
      for (const auto& overlay : selected.at("overlays").arr()) {
        auto id = overlay.at("entity_id").str(), field = overlay.at("field").str();
        if (!seen.emplace(id, field).second) throw thermal::Error("duplicate_id", id);
        entities.at(id).at(field) = overlay.at("value");
      }
    } else {
      for (const auto& [id, e] : entities)
        if (e.at("kind").str() == "case") throw thermal::Error("case_required", id);
    }
    // Preserve every source alias, including identical handles in distinct maps/namespaces.
    for (const auto& source : frozen.at("source_maps").arr()) {
      for (const auto& entry : source.at("entries").arr()) {
        thermal::SourceIdentity s{source.at("id").str(), source.at("source_revision").str(),
          source.at("source_tool").str(), source.at("source_version").str(),
          entry.at("namespace").str(), entry.at("handle").str(), entry.at("entity_id").str(), {}, {}};
        if (entry.has("submodel_handle")) s.submodel_handle = entry.at("submodel_handle").str();
        if (entry.has("node_number")) s.node_number = static_cast<std::uint64_t>(entry.at("node_number").num());
        auto i = out.source_identities.size();
        out.sources_by_entity[s.entity_id].push_back(i);
        out.source_index.emplace(std::make_tuple(s.source_map_id, s.name_space, s.handle), i);
        out.source_identities.push_back(std::move(s));
      }
    }
    std::map<std::string, const J*> laws;
    for (const auto& law : envelope.at("material_laws").arr()) {
      const auto& id = law.at("material_id").str();
      target(entities, id, "material");
      if (!laws.emplace(id, &law).second) throw thermal::Error("duplicate_id", id);
      if (law.obj().size() == 1) throw thermal::Error("schema", id);
    }
    std::map<std::string, std::size_t> node_index, material_index;
    for (const auto& [id, e] : entities) {
      auto kind = e.at("kind").str();
      try {
        if (kind == "node") {
          auto classification = e.at("classification").str();
          thermal::Node node{id, e.at("submodel_id").str(),
            classification == "capacitive" ? thermal::NodeClass::capacitive :
            classification == "algebraic" ? thermal::NodeClass::algebraic : thermal::NodeClass::prescribed,
            e.at("temperature").at("value").num(), e.at("capacity").at("value").num(), {}, {}, {}, {}, 0};
          if (node.classification != thermal::NodeClass::prescribed)
            node.equation = out.differential_count + out.algebraic_count;
          if (node.classification == thermal::NodeClass::capacitive) node.differential_index = out.differential_count++;
          if (node.classification == thermal::NodeClass::algebraic) node.algebraic_index = out.algebraic_count++;
          node_index.emplace(id, out.nodes.size());
          out.nodes.push_back(std::move(node));
        } else if (kind == "material") {
          double lo = e.at("valid_temperature").at(0).at("value").num();
          double hi = e.at("valid_temperature").at(1).at("value").num();
          auto property = [&](const std::string& name) {
            if (laws.contains(id) && laws.at(id)->has(name)) return thermal_law(laws.at(id)->at(name), name, lo, hi);
            return thermal::PropertyLaw(e.at(name).at("value").num(), lo, hi);
          };
          std::optional<thermal::Tensor> material_tensor;
          std::optional<std::string> material_frame;
          if (e.has("conductivity_tensor")) {
            if (laws.contains(id) && laws.at(id)->has("conductivity")) throw thermal::Error("unsupported_tensor_law", id);
            thermal::Tensor tensor{};
            for (std::size_t i = 0; i < 3; ++i)
              for (std::size_t j = 0; j < 3; ++j) tensor[i][j] = e.at("conductivity_tensor").at(i).at(j).num();
            material_tensor = tensor;
            material_frame = e.at("frame_id").str();
          }
          thermal::Material material{id, property("density"), property("specific_heat"), property("conductivity"), material_tensor, material_frame};
          material_index.emplace(id, out.materials.size());
          out.materials.push_back(std::move(material));
        } else if (kind != "submodel" && kind != "conductor" && kind != "load" && kind != "case") {
          // Frozen in canonical_snapshot; preparation never claims to implement their physics.
          out.deferred_entity_ids.push_back(id);
        }
      } catch (thermal::Error& error) { error.entity_id = id; throw; }
        catch (Error& error) { error.entity = id; throw; }
    }
    if (out.nodes.empty()) throw thermal::Error("empty_network");
    std::set<std::string> storage_nodes;
    for (const auto& storage : envelope.at("node_storage").arr()) {
      const auto& id = storage.at("node_id").str();
      target(entities, id, "node");
      const auto& material_id = storage.at("material_id").str();
      target(entities, material_id, "material");
      if (!storage_nodes.insert(id).second) throw thermal::Error("duplicate_id", id);
      auto& node = out.nodes.at(node_index.at(id));
      if (node.classification != thermal::NodeClass::capacitive) throw thermal::Error("range", id);
      node.material_index = material_index.at(material_id);
      try {
        node.mass = quantity(storage.at("mass"), "mass", 0, true);
        const auto& material = out.materials.at(*node.material_index);
        (void)material.density.sample(node.temperature);
        (void)material.tensor(node.temperature);
        double c = node.mass * material.specific_heat.sample(node.temperature).value;
        if (!std::isfinite(c) || std::abs(c-node.capacity) > 1e-12*std::max(c, node.capacity))
          throw thermal::Error("storage_mismatch", id);
      } catch (thermal::Error& error) { error.entity_id = id; throw; }
        catch (Error& error) { error.entity = id; throw; }
    }
    std::set<std::string> active_loads;
    if (out.case_id) {
      for (const auto& id : entities.at(*out.case_id).at("load_ids").arr()) active_loads.insert(id.str());
      for (const auto& id : entities.at(*out.case_id).at("control_ids").arr()) {
        const auto& control = entities.at(id.str());
        if (!active_loads.contains(control.at("load_id").str())) throw thermal::Error("reference", id.str());
      }
    }
    std::vector<std::size_t> parent(out.nodes.size());
    for (std::size_t i = 0; i < parent.size(); ++i) parent[i] = i;
    auto root = [&](std::size_t i) {
      while (parent[i] != i) { parent[i] = parent[parent[i]]; i = parent[i]; }
      return i;
    };
    for (const auto& [id, e] : entities) {
      if (e.at("kind").str() == "conductor") {
        thermal::Conductor c{id, node_index.at(e.at("from_node_id").str()),
          node_index.at(e.at("to_node_id").str()), e.at("conductance").at("value").num()};
        if (c.conductance > 0) parent[root(c.to)] = root(c.from);
        out.conductors.push_back(std::move(c));
      } else if (e.at("kind").str() == "load") {
        thermal::Load l{id, node_index.at(e.at("node_id").str()), e.at("power").at("value").num(), {},
          !out.case_id || active_loads.contains(id)};
        if (e.has("expression_id")) l.expression_id = e.at("expression_id").str();
        out.loads.push_back(std::move(l));
      }
    }
    std::map<std::size_t, std::size_t> components;
    for (std::size_t i = 0; i < out.nodes.size(); ++i) {
      auto key = root(i);
      if (!components.contains(key)) { components.emplace(key, out.components.size()); out.components.emplace_back(); }
      auto& component = out.components.at(components.at(key));
      component.nodes.push_back(i);
      component.prescribed_anchor |= out.nodes[i].classification == thermal::NodeClass::prescribed;
      component.storage_anchor |= out.nodes[i].classification == thermal::NodeClass::capacitive;
    }
    for (auto& component : out.components) {
      component.steady_conduction_singular = !component.prescribed_anchor;
      component.transient_algebraic_singular = !component.prescribed_anchor && !component.storage_anchor;
    }
    // Hash the complete immutable input, with canonical model and identity-sorted bindings.
    envelope.at("model") = frozen;
    for (auto key : {"material_laws", "node_storage"}) {
      auto id_key = std::string_view(key) == "material_laws" ? "material_id" : "node_id";
      std::sort(envelope.at(key).arr().begin(), envelope.at(key).arr().end(),
        [&](const J& a, const J& b) { return a.at(id_key).str() < b.at(id_key).str(); });
    }
    for (auto& law : envelope.at("material_laws").arr())
      for (auto& [name, table] : law.obj()) if (name != "material_id")
        std::sort(table.at("discontinuities").arr().begin(), table.at("discontinuities").arr().end(),
          [](const J& a, const J& b) { return a.num() < b.num(); });
    out.preparation_hash = sha256(std::string("FCST-thermal-input-v1\0",22) + canonical(envelope));
    return out;
  } catch (thermal::Error& error) {
    for (const auto& source : model.at("source_maps").arr())
      for (const auto& entry : source.at("entries").arr())
        if (entry.at("entity_id").str() == error.entity_id && error.source_map_id.empty()) error.source_map_id = source.at("id").str();
    throw;
  } catch (Error& error) {
    for (const auto& source : model.at("source_maps").arr())
      for (const auto& entry : source.at("entries").arr())
        if (entry.at("entity_id").str() == error.entity && error.source.empty()) error.source = source.at("id").str();
    throw;
  }
}
