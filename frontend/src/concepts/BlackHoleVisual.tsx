import { useEffect, useRef } from "react";
import blackHole from "../assets/eclipse-black-hole-reference.png";

const vertexShader = `
  attribute vec2 aPosition;
  varying vec2 vUv;
  void main() {
    vUv = aPosition * 0.5 + 0.5;
    gl_Position = vec4(aPosition, 0.0, 1.0);
  }
`;

const fragmentShader = `
  precision highp float;
  varying vec2 vUv;
  uniform sampler2D uPhoto;
  uniform vec2 uFit;
  uniform float uImageAspect;
  uniform float uTime;
  uniform float uListening;

  float orbitLight(vec2 point, vec2 axes, float phase, float speed) {
    vec2 ring = point / axes;
    float distanceToLane = length(ring);
    float lane = exp(-pow((distanceToLane - 1.0) / 0.17, 2.0));
    float angle = atan(ring.y, ring.x);
    float flow = sin(angle * 5.0 - uTime * speed + phase)
               * sin(angle * 3.0 - uTime * speed * 0.62 + phase * 1.7);
    return lane * smoothstep(0.25, 0.9, flow);
  }

  void main() {
    vec2 uv = (vUv - (1.0 - uFit) * 0.5) / uFit;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
      gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);
      return;
    }

    vec2 center = vec2(0.5, 0.5);
    vec2 delta = uv - center;
    float subject = (1.0 - smoothstep(0.30, 0.55, abs(delta.x)))
                  * (1.0 - smoothstep(0.25, 0.44, abs(delta.y)));
    float breathing = uListening * (0.14 + 0.009 * sin(uTime * 0.6));
    vec2 compressedUv = uv;
    compressedUv.y = center.y + delta.y / (1.0 - breathing * subject);

    vec3 color = texture2D(uPhoto, compressedUv).rgb;
    float energy = smoothstep(0.035, 0.22, dot(color, vec3(0.27, 0.60, 0.13)));

    // Four aligned currents illuminate only the matter already in the photo.
    vec2 diskPoint = vec2(delta.x * uImageAspect, compressedUv.y - center.y);
    float rotationSpeed = 0.42 + 0.22 * uListening;
    float flow = orbitLight(diskPoint, vec2(0.40, 0.085), 0.3, rotationSpeed * 1.25)
               + orbitLight(diskPoint, vec2(0.58, 0.13), 2.1, rotationSpeed)
               + orbitLight(diskPoint, vec2(0.78, 0.19), 4.2, rotationSpeed * 0.82)
               + orbitLight(diskPoint, vec2(0.98, 0.25), 1.4, rotationSpeed * 0.72);
    color *= 1.0 + energy * flow * (0.42 + 0.14 * uListening);

    color *= 1.0 + uListening * energy * 0.14;
    gl_FragColor = vec4(color, 1.0);
  }
`;

function compileShader(
  gl: WebGLRenderingContext,
  type: number,
  source: string,
) {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    console.warn("ECLIPSE shader:", gl.getShaderInfoLog(shader));
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

export function BlackHoleVisual({ listening }: { listening: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const listeningRef = useRef(listening);

  useEffect(() => {
    listeningRef.current = listening;
  }, [listening]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const gl = canvas.getContext("webgl", {
      alpha: false,
      antialias: false,
      depth: false,
      preserveDrawingBuffer: false,
    });
    if (!gl) {
      console.warn("ECLIPSE: WebGL no disponible; se muestra la imagen fija.");
      return;
    }

    const vertex = compileShader(gl, gl.VERTEX_SHADER, vertexShader);
    const fragment = compileShader(gl, gl.FRAGMENT_SHADER, fragmentShader);
    if (!vertex || !fragment) return;
    const program = gl.createProgram();
    if (!program) return;
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.warn("ECLIPSE program:", gl.getProgramInfoLog(program));
      return;
    }
    gl.useProgram(program);

    const position = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, position);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
      gl.STATIC_DRAW,
    );
    const positionLocation = gl.getAttribLocation(program, "aPosition");
    gl.enableVertexAttribArray(positionLocation);
    gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);

    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);

    const image = new Image();
    let frame = 0;
    let stopped = false;
    let started = false;
    let previous = 0;
    let compression = 0;
    const fitLocation = gl.getUniformLocation(program, "uFit");
    const aspectLocation = gl.getUniformLocation(program, "uImageAspect");
    const timeLocation = gl.getUniformLocation(program, "uTime");
    const listeningLocation = gl.getUniformLocation(program, "uListening");

    function draw(now: number) {
      if (stopped || !canvas || !gl) return;
      frame = requestAnimationFrame(draw);
      if (now - previous < 1000 / 30) return;
      const deltaTime = Math.min((now - previous) / 1000, 0.1);
      previous = now;

      const bounds = canvas.getBoundingClientRect();
      const width = Math.max(1, Math.round(bounds.width));
      const height = Math.max(1, Math.round(bounds.height));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
        gl.viewport(0, 0, width, height);
      }
      const canvasRatio = width / height;
      const imageRatio = image.naturalWidth / image.naturalHeight;
      const fitX = canvasRatio > imageRatio ? imageRatio / canvasRatio : 1;
      const fitY = canvasRatio < imageRatio ? canvasRatio / imageRatio : 1;
      compression +=
        ((listeningRef.current ? 1 : 0) - compression) *
        (1 - Math.exp(-deltaTime / 2.6));
      gl.uniform2f(fitLocation, fitX, fitY);
      gl.uniform1f(aspectLocation, imageRatio);
      gl.uniform1f(timeLocation, now / 1000);
      gl.uniform1f(listeningLocation, compression);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }

    const start = () => {
      if (stopped || started) return;
      started = true;
      gl.texImage2D(
        gl.TEXTURE_2D,
        0,
        gl.RGBA,
        gl.RGBA,
        gl.UNSIGNED_BYTE,
        image,
      );
      canvas.classList.add("is-ready");
      frame = requestAnimationFrame(draw);
    };
    image.onload = start;
    image.src = blackHole;
    if (image.complete && image.naturalWidth > 0) start();

    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      image.onload = null;
      gl.deleteTexture(texture);
      gl.deleteBuffer(position);
      gl.deleteProgram(program);
      gl.deleteShader(vertex);
      gl.deleteShader(fragment);
    };
  }, []);

  return (
    <div className="eclipse-visual">
      <img
        className="eclipse-photo"
        src={blackHole}
        alt="Visualización realista de un agujero negro y su disco de acreción"
      />
      <canvas className="eclipse-canvas" ref={canvasRef} aria-hidden="true" />
    </div>
  );
}
