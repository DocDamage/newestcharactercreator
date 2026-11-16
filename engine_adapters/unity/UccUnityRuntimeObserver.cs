#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Ucc.UnityAdapter {
 // Verification only. Expected source positions/normals never enter this process.
 public sealed class UccUnityRuntimeObserver : MonoBehaviour {
  [Serializable] public sealed class Shape {public string name;public float value;}
  [Serializable] public sealed class Pose {public string name,bone;public float[] delta_blender_world;public Shape[] shapes;}
  [Serializable] public sealed class Plan {
   public int schema_version;public string policy,request_sha256,source_manifest_sha256,native_mesh_sha256,topology_sha256;public Pose[] cases;
  }
  [Serializable] public sealed class Row {public string name,image;public int camera_index,engine_frame,vertices;public long offset;public Matrix4x4 root_world;}
  [Serializable] public sealed class Report {
   public int schema_version=1;public string policy="UCC_UNITY_GPU_OBSERVATION_V1",request_sha256,source_manifest_sha256,native_mesh_sha256,topology_sha256;
   public string unity,graphics,color_space,skin_weights;public Row[] rows;
   public bool cleanup_restored,runtime_verified=false,visual_quality_approved=false;
  }
  struct Local {public Vector3 p,s;public Quaternion r;}
  static string Root=>Directory.GetParent(Application.dataPath).FullName;
  IEnumerator Start() {
   var iterator=Run();
   while(true) {
    bool next;try {next=iterator.MoveNext();}
    catch(Exception error){Debug.LogException(error);File.WriteAllText(Path.Combine(Root,"runtime-error.txt"),error.ToString());File.WriteAllText(Path.Combine(Root,"runtime-done.txt"),"2");yield break;}
    if(!next)break;yield return iterator.Current;
   }
   File.WriteAllText(Path.Combine(Root,"runtime-done.txt"),"0");
  }
  static byte[] Read(GraphicsBuffer buffer) {
   var request=AsyncGPUReadback.Request(buffer);request.WaitForCompletion();
   if(request.hasError)throw new InvalidDataException("Actual native GPU readback failed");return request.GetData<byte>().ToArray();
  }
  static void Image(RenderTexture target,string path) {
   var previous=RenderTexture.active;RenderTexture.active=target;var image=new Texture2D(512,512,TextureFormat.RGBA32,false);
   try {image.ReadPixels(new Rect(0,0,512,512),0,0);image.Apply();File.WriteAllBytes(path,image.EncodeToPNG());}
   finally {RenderTexture.active=previous;UnityEngine.Object.DestroyImmediate(image);}
  }
  IEnumerator Run() {
   var plan=JsonUtility.FromJson<Plan>(File.ReadAllText(Path.Combine(Root,"runtime-plan.json")));
   if(plan==null||plan.schema_version!=1||plan.policy!="UCC_UNITY_RUNTIME_PLAN_V1"||plan.cases==null||plan.cases.Length!=178)
    throw new InvalidDataException("Complete bound runtime diagnostic plan required");
   var roots=UnityEngine.SceneManagement.SceneManager.GetActiveScene().GetRootGameObjects();
   if(roots.Length!=1)throw new InvalidDataException("Saved character scene root differs");var instance=roots[0];
   foreach(var animator in instance.GetComponentsInChildren<Animator>(true)) {
    if(animator.runtimeAnimatorController!=null)throw new InvalidDataException("Static verification cannot replace an animation controller");animator.enabled=false;
   }
   var skin=instance.GetComponentsInChildren<SkinnedMeshRenderer>(true).Single();var mesh=skin.sharedMesh;var hook=skin.GetComponent<UccNativeNormals>();
   if(hook==null||!hook.IsInitialized||hook.LastError!=""||UccNativeMeshIdentity.Compute(skin)!=plan.native_mesh_sha256)
    throw new InvalidDataException("Actual saved native adapter failed to initialize");
   var transforms=instance.GetComponentsInChildren<Transform>(true);var bones=transforms.ToDictionary(t=>t.name);
   var neutral=transforms.Select(t=>new Local{p=t.localPosition,r=t.localRotation,s=t.localScale}).ToArray();
   var bounds=skin.bounds;var cameras=new Camera[2];var targets=new RenderTexture[2];
   RenderSettings.ambientMode=AmbientMode.Flat;RenderSettings.ambientLight=new Color(.12f,.12f,.12f);RenderSettings.reflectionIntensity=0;
   var light=new GameObject("UCC verification light").AddComponent<Light>();light.type=LightType.Directional;light.intensity=1.5f;light.transform.rotation=Quaternion.Euler(30,155,0);RenderSettings.sun=light;
   Directory.CreateDirectory(Path.Combine(Root,"runtime-renders"));
   for(int i=0;i<2;i++) {
    var camera=new GameObject("UCC verification camera "+i).AddComponent<Camera>();camera.depth=i;camera.orthographic=true;camera.orthographicSize=bounds.size.y*.65f;
    camera.nearClipPlane=.01f;camera.farClipPlane=100;camera.transform.position=bounds.center+(i==0?new Vector3(0,0,bounds.size.y*3):new Vector3(bounds.size.y*1.4f,0,bounds.size.y*2.5f));
    camera.transform.LookAt(bounds.center,Vector3.up);camera.renderingPath=RenderingPath.Forward;camera.clearFlags=CameraClearFlags.SolidColor;
    camera.backgroundColor=new Color(.025f,.025f,.025f,0);camera.allowHDR=false;camera.allowMSAA=false;
    var target=new RenderTexture(512,512,24,RenderTextureFormat.ARGB32,RenderTextureReadWrite.sRGB);target.Create();camera.targetTexture=target;cameras[i]=camera;targets[i]=target;
   }
   for(int wait=0;hook.CompletedFrames<2;wait++){if(wait>20||hook.LastError!="")throw new InvalidDataException("Native skin warmup failed");yield return null;}
   var conversion=Matrix4x4.zero;conversion[0,0]=-1;conversion[1,2]=1;conversion[2,1]=-1;conversion[3,3]=1;var rows=new List<Row>();
   using(var output=new BinaryWriter(File.Open(Path.Combine(Root,"runtime-native.bin"),FileMode.CreateNew))) {
    foreach(var pose in plan.cases) {
     if(pose.delta_blender_world==null||pose.delta_blender_world.Length!=16||pose.shapes==null||pose.shapes.Length!=12)
      throw new InvalidDataException("Runtime diagnostic pose is incomplete");
     for(int i=0;i<transforms.Length;i++){transforms[i].localPosition=neutral[i].p;transforms[i].localRotation=neutral[i].r;transforms[i].localScale=neutral[i].s;}
     for(int i=0;i<mesh.blendShapeCount;i++)skin.SetBlendShapeWeight(i,0);
     if(!String.IsNullOrEmpty(pose.bone)) {
      var delta=Matrix4x4.zero;for(int r=0;r<4;r++)for(int c=0;c<4;c++)delta[r,c]=pose.delta_blender_world[r*4+c];delta=conversion*delta*conversion.inverse;
      var bone=bones[pose.bone];bone.SetPositionAndRotation(delta.MultiplyPoint3x4(bone.position),delta.rotation*bone.rotation);
     }
     foreach(var shape in pose.shapes) {
      int index=mesh.GetBlendShapeIndex(shape.name);
      if(index<0||float.IsNaN(shape.value)||float.IsInfinity(shape.value)||shape.value<0||shape.value>.5f)throw new InvalidDataException("Runtime facial control differs");
      skin.SetBlendShapeWeight(index,shape.value*100);
     }
     var captured=new bool[2];Exception failure=null;
     Camera.CameraCallback capture=camera=> {
      int view=Array.IndexOf(cameras,camera);if(view<0||captured[view])return;
      try {
       if(hook.LastError!=""||hook.CompletedFrame!=Time.frameCount||hook.CompletedCamera!=camera.GetInstanceID())throw new InvalidDataException("Native adapter did not complete this automatic frame/camera");
       var row=new Row{name=pose.name,camera_index=view,engine_frame=Time.frameCount,vertices=mesh.vertexCount,offset=output.BaseStream.Position,root_world=skin.rootBone.localToWorldMatrix,
        image="runtime-renders/"+rows.Count.ToString("D3")+".png"};
       using(var input=skin.GetVertexBuffer()) {
        if(input==null||input.count!=14517||input.stride!=40||hook.DrawVertexBuffer==null||hook.DrawVertexBuffer.stride!=40)throw new InvalidDataException("Actual native GPU layout differs");
        var before=Read(input);var after=Read(hook.DrawVertexBuffer);
        if(before.Length!=14517*40||after.Length!=14517*40)throw new InvalidDataException("Incomplete actual GPU readback");
        for(int vertex=0;vertex<14517;vertex++){output.Write(before,vertex*40,12);output.Write(after,vertex*40,24);}
       }
       Image(targets[view],Path.Combine(Root,row.image));rows.Add(row);captured[view]=true;
      }catch(Exception error){failure=error;}
     };
     Camera.onPostRender+=capture;yield return null;Camera.onPostRender-=capture;
     if(failure!=null)throw failure;if(!captured.All(v=>v))throw new InvalidDataException("Both automatic cameras must observe every diagnostic pose");
    }
   }
   var flags=System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.NonPublic;
   var originalMaterial=(Material)typeof(UccNativeNormals).GetField("original",flags).GetValue(hook);
   var originalTarget=(GraphicsBuffer.Target)typeof(UccNativeNormals).GetField("originalBufferTarget",flags).GetValue(hook);
   var originalRecalc=(bool)typeof(UccNativeNormals).GetField("originalMatrixRecalculation",flags).GetValue(hook);
   hook.enabled=false;
   if(hook.IsInitialized||hook.DrawVertexBuffer!=null||skin.sharedMesh!=mesh||skin.sharedMaterial!=originalMaterial||skin.vertexBufferTarget!=originalTarget||skin.forceMatrixRecalculationPerRender!=originalRecalc||cameras.Any(c=>c.GetCommandBuffers(CameraEvent.AfterForwardOpaque).Length!=0))
    throw new InvalidDataException("Runtime cleanup did not restore source state");
   hook.enabled=true;for(int wait=0;hook.CompletedFrames<2;wait++){if(wait>20||!hook.IsInitialized||hook.LastError!=""||!skin.forceMatrixRecalculationPerRender)throw new InvalidDataException("Same native component could not resume");yield return null;}
   var report=new Report{request_sha256=plan.request_sha256,source_manifest_sha256=plan.source_manifest_sha256,native_mesh_sha256=plan.native_mesh_sha256,topology_sha256=plan.topology_sha256,
    unity=Application.unityVersion,graphics=SystemInfo.graphicsDeviceType.ToString(),color_space=QualitySettings.activeColorSpace.ToString(),skin_weights=QualitySettings.skinWeights.ToString(),rows=rows.ToArray(),cleanup_restored=true};
   File.WriteAllText(Path.Combine(Root,"runtime-observation.json"),JsonUtility.ToJson(report));
   for(int i=0;i<2;i++){cameras[i].targetTexture=null;targets[i].Release();UnityEngine.Object.DestroyImmediate(targets[i]);UnityEngine.Object.DestroyImmediate(cameras[i].gameObject);}
   UnityEngine.Object.DestroyImmediate(light.gameObject);
  }
 }
}
#endif
