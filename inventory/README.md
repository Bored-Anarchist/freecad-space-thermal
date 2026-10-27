# WP-01 online example inventory

Baseline `online-examples-2026-10-27-r2` contains 55 original files from four pinned public repositories, grouped into six model/example cases. It maps 21 feature groups and all 12 proposed compatibility profiles. This is an acquired-example baseline; no profile is qualified and the complete required corpus is not frozen.

| Source | Acquired material | Rights/publication disposition |
|---|---|---|
| [HSFL Artemis hardware](https://github.com/hsfl/artemis-hardware/tree/bcc649cf7932dcc410f8a594213383fb84e68d47/Thermal), linked by the [university thermal lab](https://pressbooks-dev.oer.hawaii.edu/epet302/chapter/therma/) | Thermal Desktop DWG and optical/thermal property companions | Repository MIT license retained locally; raw DWG metadata and embedded dependencies not cleared for publication |
| [Pycanha ESATAN examples](https://github.com/pycanha-project/pycanha/tree/01c5e219c086ea25fbe00868ecd0e27994619fb3/tests/data/esatan) | Disc ERG, steady/transient D-decks and HDF5 TMD results; separate geometry/STEP-TAS feature corpus | Repository MIT license retained locally; vendor-generated data/metadata coverage still requires review before redistribution |
| [UC Davis Thermal Desktop community model](https://github.com/Space-and-Satellite-Systems-UC-Davis/Structure-Thermal-Desktop/tree/c7424e7e9be0b40527c69f84800ef6c691fc73dc) | SINDA entry deck, conduction include, environment/radiation includes, coefficient data, retained user logic and associated source output | No repository license declared; acquired as a local reference candidate; redistribution held |
| [AcubeSAT native ESATAN project](https://github.com/AcubeSAT/esatan-models/tree/18ace5b528854783dd4aba8301add7134c78bf9e/cubesat/v2) | Native ERG geometry, ERE environment, ERK kinematics, XML project descriptor, 25 analysis templates and provenance README | No repository license declared; originals held locally; no model bytes or private metadata republished |

`acquisition-sources.json` identifies exact upstream commits and selected paths. `source-lock.json` records byte counts, SHA-256 and Git blob hashes, verified against those exact upstream trees. Originals and their license notices are preserved under ignored `.local/corpus/originals/`; no original model bytes, binary metadata, source logic or raw outputs are committed. The lock contains bounded static observations and privacy categories without sensitive matched values.

`models.json` records source versions, dependencies, results, rights and per-operation dispositions. `feature-map.csv` assigns engine components, packages, owner roles and requirement IDs. `profile-coverage.csv` retains every profile, including those without examples. `gaps.json` is the risk/prerequisite register. Role assignments follow the existing work-package ownership; qualified physics/version decisions remain future evidence.

The disc decks explicitly identify ESATAN-TMS **2018 SP1**. Their TMD files have HDF5 signatures; their schemas and numeric observations have not been independently qualified. Static deck inspection counts 102 node declarations (101 D and one B), 190 GL declarations and 5050 GR declarations. These lexical classes do not establish all physical boundary/algebraic semantics. The separate FEATURES STEP file identifies a **2025** exporter and `tas_arm`; its companion geometry deliberately exercises syntax and is not a physical numerical oracle.

The Artemis drawing has DWG container signature **AC1032**. That does not identify its Thermal Desktop source release. The published property companions and the tutorial's separate heat-load worksheet still need native dependency review. The community `case1.cc` explicitly identifies **Thermal Desktop 6.3**; its exact patch and SINDA release remain unverified. Its five direct INSERT references and associated coefficient data are acquired, but indirect runtime I/O/linking still needs source execution. Its output is upstream evidence, not a new source run or a demonstrated match to FCST.

All 25 AcubeSAT case templates identify **ESATAN-TMS 2020**. This establishes the template version family; it does not establish the exact native geometry/environment/kinematics release or prove native dependency closure. Acquiring all four native companion types closes the earlier missing-container acquisition gap, while licensed reopen/run and result retrieval remain blocked.

Vendor execution is blocked: no active licensed reference runner is configured. Local runtime-access details are held outside the publication copy. No attempt is made to bypass licensing or execute imported Fortran, macros or scripts. The [CRTech samples page](https://www.crtech.com/getting-started) requires customer/evaluator access. The [STEP-TAS standard](https://ecss.nl/wp-content/uploads/2018/02/ECSS-E-ST-31-04C%281February2018%29.pdf) identifies a registration-required EXPRESS annex; the current official ECSS and ESA exchange endpoints redirect to an unavailable-site notice. The schema, dictionary and independent validator remain unacquired; searching the public STEPcode schema collection did not locate a TAS schema. No authenticated download restrictions are bypassed.

The independently authored [two-node analytic seed](../tests/fixtures/public/two-node-analytic.json) supports future native conduction/transient checks. It is a versioned physics-input/oracle seed, not an FCST storage snapshot, a tested vendor deck or evidence that a solver exists.

```text
python tools/acquire_corpus.py
python tools/lock_corpus.py
python tools/check_inventory.py
python tools/check_inventory.py --local
python tools/check_inventory.py --local --qualify
```

Acquisition requires internet access and never executes downloads. Locking also requires authenticated GitHub read access to verify pinned upstream tree metadata. CI runs the offline metadata checker and adversarial synthetic tests; it does not download or upload third-party originals. `--local` checks every retained original hash. `--qualify` deliberately returns a blocked failure while licensing, version, dependency, rights, schema, advanced/legacy coverage or reference-result gaps remain. Native model creation and solving development continues independently of those compatibility prerequisites.
