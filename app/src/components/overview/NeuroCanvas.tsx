import { useEffect, useRef } from 'react'

export default function NeuroCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationRef = useRef<number | null>(null)
  const stateRef = useRef({ time: 0, pointerX: 0.5, pointerY: 0.5 })
  const dimsRef = useRef({ width: 800, height: 400 })

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    // Get WebGL context with proper typing
    let gl: WebGLRenderingContext | null = null
    try {
      gl = canvas.getContext('webgl') as unknown as WebGLRenderingContext
      if (!gl) {
        gl = canvas.getContext('experimental-webgl') as unknown as WebGLRenderingContext
      }
    } catch (e) {
      console.warn('WebGL not supported')
      return
    }

    if (!gl) {
      console.warn('WebGL not available')
      return
    }

    // Vertex shader
    const vertexShaderSource = `
      precision mediump float;
      attribute vec2 a_position;
      varying vec2 vUv;
      void main() {
        vUv = 0.5 * (a_position + 1.0);
        gl_Position = vec4(a_position, 0.0, 1.0);
      }
    `

    // Fragment shader - procedural neuro effect
    const fragmentShaderSource = `
      precision mediump float;
      varying vec2 vUv;
      uniform float u_time;
      uniform float u_ratio;
      uniform vec2 u_pointer;

      vec2 rot(vec2 uv, float th) {
        return mat2(cos(th), sin(th), -sin(th), cos(th)) * uv;
      }

      float neuro(vec2 uv, float t, float p) {
        vec2 sa = vec2(0.0);
        vec2 res = vec2(0.0);
        float sc = 8.0;
        for (int j = 0; j < 14; j++) {
          uv = rot(uv, 1.0);
          sa = rot(sa, 1.0);
          vec2 layer = uv * sc + float(j) + sa - t;
          sa += sin(layer) + 2.4 * p;
          res += (0.5 + 0.5 * cos(layer)) / sc;
          sc *= 1.2;
        }
        return res.x + res.y;
      }

      void main() {
        vec2 uv = 0.5 * vUv;
        uv.x *= u_ratio;
        vec2 ptr = vUv - u_pointer;
        ptr.x *= u_ratio;
        float p = clamp(length(ptr), 0.0, 1.0);
        p = 0.5 * pow(1.0 - p, 2.0);
        float t = 0.001 * u_time;
        float n = neuro(uv, t, p);
        n = 1.2 * pow(n, 3.0);
        n += pow(n, 10.0);
        n = max(0.0, n - 0.5);
        n *= (1.0 - length(vUv - 0.5));
        vec3 col = vec3(0.55, 0.35, 0.95);
        col = mix(col, vec3(0.05, 0.78, 0.74), 0.34 + 0.16 * sin(2.0 * t));
        col += vec3(0.96, 0.66, 0.18) * (0.25 + 0.55 * p);
        col = col * n;
        gl_FragColor = vec4(col, n);
      }
    `

    const compileShader = (source: string, type: number) => {
      const shader = gl!.createShader(type)
      if (!shader) return null
      gl!.shaderSource(shader, source)
      gl!.compileShader(shader)
      if (!gl!.getShaderParameter(shader, gl!.COMPILE_STATUS)) {
        console.error('Shader compile error:', gl!.getShaderInfoLog(shader))
        return null
      }
      return shader
    }

    const vs = compileShader(vertexShaderSource, gl.VERTEX_SHADER)
    const fs = compileShader(fragmentShaderSource, gl.FRAGMENT_SHADER)
    if (!vs || !fs) return

    const program = gl.createProgram()
    if (!program) return
    gl.attachShader(program, vs)
    gl.attachShader(program, fs)
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error('Program link error:', gl.getProgramInfoLog(program))
      return
    }

    gl.useProgram(program)

    // Create buffer
    const buffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW)

    // Set up attributes
    const positionLoc = gl.getAttribLocation(program, 'a_position')
    gl.enableVertexAttribArray(positionLoc)
    gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0)

    // Set up blending
    gl.enable(gl.BLEND)
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE)

    // Get uniform locations
    const uTimeLoc = gl.getUniformLocation(program, 'u_time')
    const uRatioLoc = gl.getUniformLocation(program, 'u_ratio')
    const uPointerLoc = gl.getUniformLocation(program, 'u_pointer')

    // Track mouse movement
    const handleMouseMove = (e: MouseEvent) => {
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      stateRef.current.pointerX = (e.clientX - rect.left) / rect.width
      stateRef.current.pointerY = (e.clientY - rect.top) / rect.height
    }

    canvas.addEventListener('mousemove', handleMouseMove)
    canvas.addEventListener('mouseleave', () => {
      stateRef.current.pointerX = 0.5
      stateRef.current.pointerY = 0.5
    })

    // Seed initial canvas size from parent
    const parent = canvas.parentElement
    if (parent) {
      canvas.width = parent.clientWidth || 800
      canvas.height = parent.clientHeight || 400
      dimsRef.current = { width: canvas.width, height: canvas.height }
    }

    // Keep canvas buffer in sync with container size
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        const w = Math.round(width) || 1
        const h = Math.round(height) || 1
        canvas.width = w
        canvas.height = h
        dimsRef.current = { width: w, height: h }
        gl?.viewport(0, 0, w, h)
      }
    })
    if (parent) observer.observe(parent)

    // Animation loop
    const animate = () => {
      stateRef.current.time += 1
      const state = stateRef.current
      const { width, height } = dimsRef.current
      const ratio = width / (height || 1)

      gl!.viewport(0, 0, canvas.width, canvas.height)
      gl!.uniform1f(uTimeLoc, state.time)
      gl!.uniform1f(uRatioLoc, ratio)
      gl!.uniform2f(uPointerLoc, state.pointerX, state.pointerY)

      gl!.drawArrays(gl!.TRIANGLE_STRIP, 0, 4)

      animationRef.current = requestAnimationFrame(animate)
    }

    animationRef.current = requestAnimationFrame(animate)

    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current)
      canvas.removeEventListener('mousemove', handleMouseMove)
      observer.disconnect()
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      id="hermes-neuro"
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        opacity: 0.38,
        mixBlendMode: 'screen',
        pointerEvents: 'none',
      }}
    />
  )
}
