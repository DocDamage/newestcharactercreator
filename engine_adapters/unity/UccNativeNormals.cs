using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering;

namespace Ucc.UnityAdapter {
 public interface IUccNativePositionCorrection : IDisposable {
  void Record(CommandBuffer commands,GraphicsBuffer nativeSkin,GraphicsBuffer ownedDraw);
 }

 public interface IUccNativePositionCorrectionBinding {
  IUccNativePositionCorrection CreateCorrection(int[] nativeToSource);
 }

 [DisallowMultipleComponent,RequireComponent(typeof(SkinnedMeshRenderer))]
 public sealed class UccNativeNormals : MonoBehaviour {
  public const string Policy="UCC_UNITY_BUILTIN_FORWARD_QUAD_NORMALS_V1";
  [SerializeField] TextAsset sourceData;
  [SerializeField] string sourceDataSha256;
  [SerializeField] ComputeShader normalShader;
  [SerializeField] Shader warmupShader;
  [SerializeField] bool requiresPositionCorrection;
  [SerializeField] ScriptableObject positionCorrectionBinding;
  sealed class Pending {public Camera camera;public CommandBuffer commands;public GraphicsBuffer input;public int frame;}
  readonly Dictionary<int,Pending> pending=new Dictionary<int,Pending>();
  SkinnedMeshRenderer source;Mesh sourceMesh,display;UccQuadSourceData topology;
  GraphicsBuffer destination;ComputeBuffer first,ids,faces,offsets,adjacency,faceNormals;
  Material original,warmup;Material[] materials;int faceKernel,pointKernel,copyKernel,warmupFrames;
  GraphicsBuffer.Target originalBufferTarget;bool ownsBufferTarget;
  bool originalMatrixRecalculation,ownsMatrixRecalculation;
  IUccNativePositionCorrection positionCorrection;
  public string LastError {get;private set;}="";
  public bool IsInitialized {get;private set;}
  public int CompletedFrame {get;private set;}=-1;
  public int CompletedCamera {get;private set;}=-1;
  public int CompletedFrames {get;private set;}
  public GraphicsBuffer DrawVertexBuffer=>destination;
  public bool PositionCorrectionActive=>IsInitialized&&positionCorrection!=null;

#if UNITY_EDITOR
  public void ConfigureForExport(TextAsset data,string digest,ComputeShader compute,Shader hidden) {
   ConfigureForExport(data,digest,compute,hidden,null);
  }
  public void ConfigureForExport(TextAsset data,string digest,ComputeShader compute,Shader hidden,ScriptableObject correctionBinding) {
   if(Application.isPlaying)throw new InvalidOperationException("Export configuration cannot modify a running character");
   if(correctionBinding!=null&&!(correctionBinding is IUccNativePositionCorrectionBinding))
    throw new InvalidDataException("Registered position correction requires its explicit saved binding");
   sourceData=data;sourceDataSha256=digest;normalShader=compute;warmupShader=hidden;
   positionCorrectionBinding=correctionBinding;requiresPositionCorrection=correctionBinding!=null;
  }
#endif
  void SetupPositionCorrection() {
   if(!requiresPositionCorrection&&positionCorrectionBinding==null)return;
   if(!requiresPositionCorrection||positionCorrectionBinding==null||
     !(positionCorrectionBinding is IUccNativePositionCorrectionBinding binding))
    throw new InvalidDataException("Saved registered position-correction binding is missing or invalid");
   positionCorrection=binding.CreateCorrection(topology.native_source);
   if(positionCorrection==null)throw new InvalidDataException("Registered position correction did not initialize");
  }
  static ComputeBuffer Buffer<T>(T[] values,int stride) where T:struct {
   var result=new ComputeBuffer(values.Length,stride);try{result.SetData(values);return result;}catch{result.Release();throw;}
  }
  void OnEnable() {
   if(!Application.isPlaying)return;
   LastError="";CompletedFrame=-1;CompletedFrames=0;warmupFrames=0;
   try {
    source=GetComponent<SkinnedMeshRenderer>();
    if(Application.unityVersion!="6000.4.5f1"||SystemInfo.graphicsDeviceType!=GraphicsDeviceType.Direct3D11||!SystemInfo.supportsComputeShaders)
     throw new InvalidDataException("This verified profile requires Unity 6000.4.5f1 and Direct3D 11 compute rendering");
    if(QualitySettings.activeColorSpace!=ColorSpace.Linear||QualitySettings.skinWeights!=SkinWeights.Unlimited||source.quality!=SkinQuality.Auto)
     throw new InvalidDataException("Character requires Linear color and Unlimited skin weights with renderer quality Auto");
    if(source.sharedMesh==null||source.rootBone==null||!source.enabled||!source.updateWhenOffscreen)
     throw new InvalidDataException("Character needs its saved enabled native mesh, root bone and offscreen updates");
    if(normalShader==null||warmupShader==null||warmupShader.name!="Hidden/UCC/NativeSkinWarmup")throw new InvalidDataException("Saved normal shader references are missing or unsupported");
    sourceMesh=source.sharedMesh;topology=UccQuadSourceData.Read(sourceData,sourceDataSha256,source);
    foreach(var attribute in new[]{VertexAttribute.Position,VertexAttribute.Normal,VertexAttribute.Tangent})
     if(sourceMesh.GetVertexAttributeFormat(attribute)!=VertexAttributeFormat.Float32||sourceMesh.GetVertexAttributeDimension(attribute)!=(attribute==VertexAttribute.Tangent?4:3))throw new InvalidDataException("Native vertex attributes require the verified float32 layout");
    materials=source.sharedMaterials;
    if(materials.Length!=1||materials[0]==null||materials[0].shader.name!="Standard"||source.HasPropertyBlock())
     throw new InvalidDataException("This profile requires the original single Standard material without per-renderer overrides");
    original=materials[0];
    if(original.GetFloat("_Mode")!=0||original.GetTexture("_MainTex")!=null||original.GetTexture("_BumpMap")!=null||original.GetTexture("_MetallicGlossMap")!=null)
     throw new InvalidDataException("This profile requires the saved opaque color/roughness material without texture maps");
    SetupPositionCorrection();
    first=Buffer(topology.FirstNative,4);ids=Buffer(topology.native_source,4);faces=Buffer(topology.quads,16);
    offsets=Buffer(topology.Offsets,4);adjacency=Buffer(topology.Adjacency,8);faceNormals=new ComputeBuffer(topology.quads.Length,12);
    display=new Mesh{name="UCC native GPU draw buffer",indexFormat=sourceMesh.indexFormat};display.vertexBufferTarget|=GraphicsBuffer.Target.Raw;
    display.SetVertexBufferParams(sourceMesh.vertexCount,new VertexAttributeDescriptor(VertexAttribute.Position,VertexAttributeFormat.Float32,3,0),
     new VertexAttributeDescriptor(VertexAttribute.Normal,VertexAttributeFormat.Float32,3,0),new VertexAttributeDescriptor(VertexAttribute.Tangent,VertexAttributeFormat.Float32,4,0),
     new VertexAttributeDescriptor(VertexAttribute.TexCoord0,VertexAttributeFormat.Float32,2,1));
    display.SetVertexBufferData(sourceMesh.uv,0,0,sourceMesh.vertexCount,1);display.triangles=sourceMesh.triangles;display.bounds=sourceMesh.bounds;
    destination=display.GetVertexBuffer(0);if(destination.stride!=40)throw new InvalidDataException("Owned draw buffer layout is unsupported");
    faceKernel=normalShader.FindKernel("Faces");pointKernel=normalShader.FindKernel("Points");copyKernel=normalShader.FindKernel("Copy");
    warmup=new Material(warmupShader){name="UCC transient native skin pass"};source.sharedMaterials=new[]{warmup};
    originalBufferTarget=source.vertexBufferTarget;source.vertexBufferTarget|=GraphicsBuffer.Target.Raw;ownsBufferTarget=true;
    originalMatrixRecalculation=source.forceMatrixRecalculationPerRender;
    source.forceMatrixRecalculationPerRender=true;ownsMatrixRecalculation=true;
    Camera.onPostRender+=Complete;IsInitialized=true;
   }catch(Exception error){Fail(error);}
  }
  static void CheckRoot(Matrix4x4 matrix) {
   for(int r=0;r<4;r++)for(int c=0;c<4;c++)if(float.IsNaN(matrix[r,c])||float.IsInfinity(matrix[r,c]))throw new InvalidDataException("Nonfinite native root matrix");
   for(int c=0;c<3;c++) {
    Vector3 column=matrix.GetColumn(c);if(Math.Abs(column.sqrMagnitude-1)>1e-5)throw new InvalidDataException("Scaled or sheared root requires a separately verified profile");
    for(int other=0;other<c;other++)if(Math.Abs(Vector3.Dot(column,matrix.GetColumn(other)))>1e-5)throw new InvalidDataException("Sheared root is unsupported");
   }
   if(matrix.determinant<0)throw new InvalidDataException("Negative native root scale is unsupported");
  }
  void OnWillRenderObject() {
   if(!IsInitialized||!enabled)return;var camera=Camera.current;if(camera==null)return;
   int key=camera.GetInstanceID();if(pending.ContainsKey(key))return;
   GraphicsBuffer input=null;CommandBuffer command=null;
   try {
    if(camera.actualRenderingPath!=RenderingPath.Forward)throw new InvalidDataException("Only Built-in Forward cameras are admitted by this profile");
    if(source.sharedMesh!=sourceMesh||source.quality!=SkinQuality.Auto||QualitySettings.skinWeights!=SkinWeights.Unlimited||!source.forceMatrixRecalculationPerRender||source.HasPropertyBlock())throw new InvalidDataException("Native renderer input or quality changed while the adapter was active");
    var current=source.sharedMaterials;if(current.Length!=1||current[0]!=warmup)throw new InvalidDataException("Native material ownership changed while the adapter was active");
    input=source.GetVertexBuffer();if(input==null){if(++warmupFrames>4)throw new InvalidDataException("Native GPU buffer remained unavailable");return;}
    if(input.stride!=40||input.count!=display.vertexCount)throw new InvalidDataException("Native vertex buffer layout changed");
    if(source.rootBone==null)throw new InvalidDataException("Native root bone is missing");
    var root=source.rootBone.localToWorldMatrix;CheckRoot(root);
    command=new CommandBuffer{name="UCC current-frame native geometric normals"};
    command.SetComputeIntParam(normalShader,"_Stride",40);command.SetComputeIntParam(normalShader,"_PositionOffset",0);command.SetComputeIntParam(normalShader,"_NormalOffset",12);
    command.SetComputeIntParam(normalShader,"_FaceCount",topology.quads.Length);command.SetComputeIntParam(normalShader,"_VertexCount",display.vertexCount);
    foreach(int kernel in new[]{faceKernel,pointKernel}) {
     command.SetComputeBufferParam(normalShader,kernel,"_FirstNative",first);command.SetComputeBufferParam(normalShader,kernel,"_NativeSource",ids);
     command.SetComputeBufferParam(normalShader,kernel,"_Faces",faces);command.SetComputeBufferParam(normalShader,kernel,"_Offsets",offsets);
     command.SetComputeBufferParam(normalShader,kernel,"_Adjacency",adjacency);command.SetComputeBufferParam(normalShader,kernel,"_FaceNormals",faceNormals);
     command.SetComputeBufferParam(normalShader,kernel,"_Vertices",destination);
    }
    command.SetComputeBufferParam(normalShader,copyKernel,"_Input",input);command.SetComputeBufferParam(normalShader,copyKernel,"_Vertices",destination);
    command.DispatchCompute(normalShader,copyKernel,(display.vertexCount+63)/64,1,1);
    positionCorrection?.Record(command,input,destination);
    command.DispatchCompute(normalShader,faceKernel,(topology.quads.Length+63)/64,1,1);
    command.DispatchCompute(normalShader,pointKernel,(display.vertexCount+63)/64,1,1);command.DrawMesh(display,root,original,0,0);
    camera.AddCommandBuffer(CameraEvent.AfterForwardOpaque,command);pending.Add(key,new Pending{camera=camera,commands=command,input=input,frame=Time.frameCount});
   }catch(Exception error){input?.Dispose();command?.Release();Fail(error);}
  }
  void Complete(Camera camera) {
   int key=camera.GetInstanceID();if(!pending.TryGetValue(key,out var entry))return;
   camera.RemoveCommandBuffer(CameraEvent.AfterForwardOpaque,entry.commands);entry.commands.Release();entry.input.Dispose();pending.Remove(key);
   CompletedFrame=entry.frame;CompletedCamera=key;CompletedFrames++;
  }
  void Fail(Exception error){LastError=error.GetType().Name+": "+error.Message;Debug.LogError("UCC_NATIVE_NORMALS_ERROR "+LastError,this);Cleanup();enabled=false;}
  static void Release(ref ComputeBuffer buffer){buffer?.Release();buffer=null;}
  static void DestroyOwned(UnityEngine.Object value){if(value!=null){if(Application.isPlaying)Destroy(value);else DestroyImmediate(value);}}
  void Cleanup() {
   IsInitialized=false;Camera.onPostRender-=Complete;
   foreach(var entry in pending.Values){if(entry.camera!=null)entry.camera.RemoveCommandBuffer(CameraEvent.AfterForwardOpaque,entry.commands);entry.commands.Release();entry.input.Dispose();}pending.Clear();
   positionCorrection?.Dispose();positionCorrection=null;
   if(source!=null&&materials!=null&&warmup!=null){var current=source.sharedMaterials;if(current.Length==1&&current[0]==warmup)source.sharedMaterials=materials;}
   if(source!=null&&source.sharedMesh==sourceMesh&&ownsBufferTarget&&source.vertexBufferTarget==(originalBufferTarget|GraphicsBuffer.Target.Raw))source.vertexBufferTarget=originalBufferTarget;
   ownsBufferTarget=false;
   if(source!=null&&source.sharedMesh==sourceMesh&&ownsMatrixRecalculation&&source.forceMatrixRecalculationPerRender)
    source.forceMatrixRecalculationPerRender=originalMatrixRecalculation;
   ownsMatrixRecalculation=false;
   destination?.Dispose();destination=null;Release(ref first);Release(ref ids);Release(ref faces);Release(ref offsets);Release(ref adjacency);Release(ref faceNormals);
   DestroyOwned(display);display=null;DestroyOwned(warmup);warmup=null;
  }
  void OnDisable(){Cleanup();}
 }
}
