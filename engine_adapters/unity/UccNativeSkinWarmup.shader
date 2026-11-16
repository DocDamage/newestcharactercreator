Shader "Hidden/UCC/NativeSkinWarmup" {
 SubShader {
  Tags { "RenderType"="Opaque" "Queue"="Geometry" }
  Pass {
   Tags { "LightMode"="ForwardBase" }
   ColorMask 0
   ZWrite Off
   CGPROGRAM
   #pragma vertex vert
   #pragma fragment frag
   #pragma target 4.5
   #include "UnityCG.cginc"
   float4 vert(appdata_full input):SV_POSITION {return UnityObjectToClipPos(input.vertex);}
   float4 frag():SV_Target {return float4(0,0,0,0);}
   ENDCG
  }
  UsePass "Standard/SHADOWCASTER"
 }
}
