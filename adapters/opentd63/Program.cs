// SPDX-License-Identifier: MIT OR Apache-2.0
// FCST-owned sidecar. Build against an installed OpenTDv63; never bundle its DLLs.
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Collections;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using OpenTDv63;
using OpenTDv63.Dimension;

static class Program {
 sealed class BridgeException : Exception { public BridgeException(string code) : base(code) {} }
 sealed class ReferenceComparer : IEqualityComparer<object> {
  public new bool Equals(object a,object b) { return Object.ReferenceEquals(a,b); }
  public int GetHashCode(object value) { return System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(value); }
 }
 const string Profile = "opentd-6.3/1";
 static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 16*1024*1024, RecursionLimit = 40 };
 static int items;
 static string Hash(byte[] bytes) { using(var hash=SHA256.Create())return BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-","").ToLowerInvariant(); }
 static void Fail(string code) { throw new BridgeException(code); }
 static string Text(IDictionary<string,object> value,string key) {
  object raw; if(!value.TryGetValue(key,out raw) || !(raw is string)) { Fail("request_fields"); return null; }
  return (string)raw;
 }
 static string InRoot(string root,string name) {
  if(String.IsNullOrEmpty(name)||Path.IsPathRooted(name)||name.Contains(":"))Fail("unsafe_path");
  var full=Path.GetFullPath(Path.Combine(root,name));
  if(!full.StartsWith(root.TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))Fail("unsafe_path");
  var current=full;
  while(current!=null) { if((File.Exists(current)||Directory.Exists(current)) && (File.GetAttributes(current)&FileAttributes.ReparsePoint)!=0)Fail("linked_path");current=Path.GetDirectoryName(current); }
  return full;
 }
 static Dictionary<string,object> Probe() {
  var assembly=typeof(ThermalDesktop).Assembly;
  var target=CustomAttributeData.GetCustomAttributes(assembly).FirstOrDefault(a=>a.AttributeType.FullName=="System.Runtime.Versioning.TargetFrameworkAttribute");
  return new Dictionary<string,object> {{"profile",Profile},{"assembly_version",assembly.GetName().Version.ToString()},
   {"assembly_sha256",Hash(File.ReadAllBytes(assembly.Location))},{"target_framework",target==null?"unknown":target.ConstructorArguments[0].Value},
   {"qualified",false},{"execution_mode","reference_external"}};
 }
 static object Value(object value,int depth,HashSet<object> ancestors) {
  if(++items>200000 || depth>16) { Fail("inventory_limit");return null; }
  if(value==null)return null;
  var type=value.GetType();
  if(value is string) {
   var text=(string)value;
   if(text.Length>65536)return new Dictionary<string,object>{{"retained_opaque_sha256",Hash(System.Text.Encoding.UTF8.GetBytes(text))},{"characters",text.Length}};
   return text;
  }
  if(value is DateTime)return ((DateTime)value).ToString("o",System.Globalization.CultureInfo.InvariantCulture);
  if(value is Guid)return ((Guid)value).ToString("D");
  if(type.IsEnum)return value.ToString();
  if(type.IsPrimitive || value is decimal) {
   if(value is double && (Double.IsNaN((double)value)||Double.IsInfinity((double)value)))Fail("inventory_nonfinite");
   return value;
  }
  if(type.Namespace=="OpenTDv63.Dimension" && type.IsGenericType && type.GetGenericTypeDefinition().Name=="Dimensional`1") {
   return new Dictionary<string,object>{{"dimension",type.GetGenericArguments()[0].Name},{"si_value",type.GetMethod("GetValueSI").Invoke(value,new object[0])}};
  }
  if(ancestors.Contains(value))return new Dictionary<string,object>{{"retained_reference",type.FullName}};
  ancestors.Add(value);
  try {
   var dictionary=value as IDictionary;
   if(dictionary!=null) {
    var output=new Dictionary<string,object>();
    foreach(DictionaryEntry entry in dictionary)output[Convert.ToString(entry.Key,System.Globalization.CultureInfo.InvariantCulture)]=Value(entry.Value,depth+1,ancestors);
    return output;
   }
   var enumerable=value as IEnumerable;
   if(enumerable!=null) { var output=new List<object>();foreach(var item in enumerable)output.Add(Value(item,depth+1,ancestors));return output; }
   var result=new Dictionary<string,object>();
   foreach(var property in type.GetProperties(BindingFlags.Public|BindingFlags.Instance)) {
    if(property.GetIndexParameters().Length!=0 || !property.CanRead || property.Name.StartsWith("_") || property.Name=="TD" || property.Name=="TdProxy")continue;
    try { result[property.Name]=Value(property.GetValue(value,null),depth+1,ancestors); }
    catch(TargetInvocationException) { result[property.Name]=new Dictionary<string,object>{{"unsupported","api_getter_failed"}}; }
   }
   foreach(var field in type.GetFields(BindingFlags.Public|BindingFlags.Instance)) {
    if(field.Name.StartsWith("_"))continue;
    result[field.Name]=Value(field.GetValue(value),depth+1,ancestors);
   }
   return result;
  } finally { ancestors.Remove(value); }
 }
 static Dictionary<string,object> Inspect(ThermalDesktop td) {
  items=0;
  var model=td.GetModel();
  var data=new Dictionary<string,object>();
  // Model collections include GMM/TMM, surfaces, solids, nodes, properties,
  // optical assignments, source procedures, controls and all case settings.
  foreach(var property in model.GetType().GetProperties(BindingFlags.Public|BindingFlags.Instance)) {
   if(property.Name=="TD" || property.GetIndexParameters().Length!=0 || !property.CanRead)continue;
   data[property.Name]=Value(property.GetValue(model,null),0,new HashSet<object>(new ReferenceComparer()));
  }
  return new Dictionary<string,object> {{"profile",Profile},{"api",Probe()},{"units","SI"},{"collections",data},
   {"dependency_paths",new Dictionary<string,object>{{"thermal_properties",td.GetThermoPropDBPathname()},{"optical_properties",td.GetOpticalPropDBPathname()}}},
   {"qualified",false},{"execution_mode","reference_external"}};
 }
 static readonly Dictionary<string,string[]> Editable=new Dictionary<string,string[]> {
  {"Node",new[]{"InitialTemp","MassVol"}}, {"Conductor",new[]{"Value"}}, {"HeatLoad",new[]{"Value"}},
  {"Rectangle",new[]{"XMax","YMax","TopThickness","BotThickness"}}, {"ThermoProps",new[]{"Density","SpecificHeat","Conductivity"}},
  {"OpticalProps",new[]{"Alph","Emis"}}
 };
 static void Edit(ThermalDesktop td,IDictionary<string,object> edit) {
  var kind=Text(edit,"kind");var handle=Text(edit,"handle");var field=Text(edit,"field");
  if(!Editable.ContainsKey(kind)||!Editable[kind].Contains(field)||edit.Count!=4)Fail("unsupported_edit");
  object raw; if(!edit.TryGetValue("value",out raw)||raw is bool||!(raw is int||raw is long||raw is double||raw is decimal))Fail("edit_number");
  var number=Convert.ToDouble(raw,System.Globalization.CultureInfo.InvariantCulture);
  if(Double.IsNaN(number)||Double.IsInfinity(number))Fail("edit_number");
  var method=typeof(ThermalDesktop).GetMethod("Get"+kind,new[]{typeof(string),typeof(bool)});
  object entity;
  if(method!=null)entity=method.Invoke(td,new object[]{handle,true});
  else { method=typeof(ThermalDesktop).GetMethod("Get"+kind,new[]{typeof(string)});if(method==null){Fail("unsupported_edit");return;}entity=method.Invoke(td,new object[]{handle}); }
  var property=entity.GetType().GetProperty(field);
  if(property==null||!property.CanWrite)Fail("unsupported_edit");
  object converted;
  if(property.PropertyType==typeof(double))converted=number;
  else if(property.PropertyType.IsGenericType && property.PropertyType.GetGenericTypeDefinition().Name=="Dimensional`1")converted=Activator.CreateInstance(property.PropertyType,new object[]{number,Units.SI});
  else { Fail("unsupported_edit_type");return; }
  property.SetValue(entity,converted,null);
  entity.GetType().GetMethod("Update",Type.EmptyTypes).Invoke(entity,new object[0]);
 }
 static void CreateReference(ThermalDesktop td,bool run,string root) {
  var warm=td.CreateNode(new Point3d(0,0,0));warm.Submodel="FCST";warm.Id=1;warm.NodeType=RcNodeData.NodeTypes.DIFFUSION;
  warm.UseMaterial=0;warm.MassVol=100;warm.InitialTemp=new Dimensional<Temp>(293.15,Units.SI);warm.Update();
  var fixedNode=td.CreateNode(new Point3d(1,0,0));fixedNode.Submodel="FCST";fixedNode.Id=2;fixedNode.NodeType=RcNodeData.NodeTypes.BOUNDARY;
  fixedNode.UseMaterial=0;fixedNode.MassVol=0;fixedNode.InitialTemp=new Dimensional<Temp>(300,Units.SI);fixedNode.Update();
  var conductor=td.CreateConductor(new Connection(warm),new Connection(fixedNode));conductor.Submodel="FCST";conductor.Id=1;conductor.Value=2;conductor.Update();
  var heat=td.CreateHeatLoad(new Connection(warm));heat.Submodel="FCST";heat.Value=5;heat.Update();
  foreach(var transient in new[]{false,true}) {
   var name=transient?"transient":"steady";
   var cs=td.CreateCaseSet("FCST",name,"FCST-owned synthetic reference");
   cs.CalculateRadiation=0;cs.BuildSindaModel=1;cs.RunSinda=run?1:0;cs.SteadyState=transient?0:1;cs.Transient=transient?1:0;
   cs.UseUserDirectory=1;cs.UserDirectory=root;cs.SindaFilename=name;cs.AsciiTemp=1;cs.AsciiQ=1;
   cs.SindaControl.timend=new Dimensional<OpenTDv63.Dimension.Time>(100,Units.SI);
   cs.SindaControl.output=new Dimensional<OpenTDv63.Dimension.Time>(1,Units.SI);cs.Update();
   if(run)cs.Run();
  }
 }
 static object Execute(IDictionary<string,object> request) {
  var operation=Text(request,"operation");
  if(Text(request,"profile")!=Profile)Fail("profile_version");
  if(operation=="probe") { if(request.Count!=2)Fail("request_fields");return Probe(); }
  if(operation=="api-smoke") {
   if(request.Count!=2)Fail("request_fields");
   var temperature=new Dimensional<Temp>(300,Units.SI).GetValueSI();
   var time=new Dimensional<OpenTDv63.Dimension.Time>(10,Units.SI).GetValueSI();
   if(temperature!=300||time!=10)Fail("api_units");
   var sample=new Node();sample.Id=1;sample.Submodel="MAIN";sample.NodeType=RcNodeData.NodeTypes.DIFFUSION;
   sample.UseMaterial=0;sample.MassVol=100;sample.InitialTemp=new Dimensional<Temp>(300,Units.SI);
   items=0;var example=(Dictionary<string,object>)Value(sample,0,new HashSet<object>(new ReferenceComparer()));example["Handle"]="A1";
   return new Dictionary<string,object>{{"profile",Profile},{"api",Probe()},{"status","passed"},{"node_example",example},
    {"scope","offline API types and unit conversion; no host or solver qualification"}};
  }
  if(operation!="inspect"&&operation!="edit"&&operation!="create-reference"&&operation!="run-reference")Fail("unsupported_operation");
  var allowed=new HashSet<string>(new[]{"profile","operation","root","drawing","host","thermal_database","optical_database","edits","authorization_sha256"});
  if(request.Keys.Any(k=>!allowed.Contains(k)))Fail("request_fields");
  if(Text(request,"authorization_sha256").Length!=64)Fail("authorization_required");
  var root=Path.GetFullPath(Text(request,"root"));
  var drawing=InRoot(root,Text(request,"drawing"));
  var host=Path.GetFullPath(Text(request,"host"));
  if(!File.Exists(host)||!Path.GetFileName(host).Equals("acad.exe",StringComparison.OrdinalIgnoreCase))Fail("licensed_host_unavailable");
  var creating=operation=="create-reference"||operation=="run-reference";
  if(creating&&File.Exists(drawing))Fail("reference_requires_new_drawing");
  if(!creating&&!File.Exists(drawing))Fail("drawing_missing");
  var td=new ThermalDesktop();var connected=false;
  try {
   var config=new TdConnectConfig();config.Type=TdConnectConfig.Types.START_NEW_TD;config.AcadVisible=false;config.ShowAcadSplashScreen=false;
   config.AcadExePathname=host;config.StartDirectory=root;
   if(!creating)config.DwgPathname=drawing;
   td.Connect(config);connected=true;td.SetUnits(Units.SI);
   foreach(var pair in new[]{new[]{"thermal_database","thermal"},new[]{"optical_database","optical"}}) {
    object raw;if(request.TryGetValue(pair[0],out raw)&&raw is string&&!String.IsNullOrEmpty((string)raw)) {
     var path=InRoot(root,(string)raw);if(!File.Exists(path))Fail("database_missing");
     if(pair[1]=="thermal")td.OpenThermoPropDB(path);else td.OpenOpticalPropDB(path);
    }
   }
   if(creating)CreateReference(td,operation=="run-reference",root);
   if(operation=="edit") {
    object raw;if(!request.TryGetValue("edits",out raw)||!(raw is object[]))Fail("edit_fields");
    foreach(var edit in (object[])raw)Edit(td,(IDictionary<string,object>)edit);
   }
   if(operation!="inspect")td.SaveAs(drawing);
   return Inspect(td);
  } finally { if(connected)td.Quit(false); }
 }
 static int Main(string[] args) {
  try {
   if(args.Length!=2)Fail("request_arguments");
   if(new FileInfo(args[0]).Length>1048576)Fail("request_limit");
   var request=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(args[0]));
   var result=Execute(request);var output=Json.Serialize(result);
   if(output.Length>16*1024*1024)Fail("inventory_limit");
   File.WriteAllText(args[1],output);Console.WriteLine("{\"status\":\"passed\"}");return 0;
  } catch(Exception error) {
   // Never print vendor exception messages, local paths, source text or keys.
   var code=error is BridgeException?error.Message:"bridge_operation_failed";
   Console.WriteLine(Json.Serialize(new Dictionary<string,object>{{"status","failed"},{"code",code}}));return 2;
  }
 }
}
