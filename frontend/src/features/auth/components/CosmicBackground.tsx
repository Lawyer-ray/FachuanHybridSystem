import { useEffect, useMemo, useState } from 'react'
import Particles, { initParticlesEngine } from '@tsparticles/react'
import { loadSlim } from '@tsparticles/slim'
import type { ISourceOptions } from '@tsparticles/engine'
import { useTheme } from 'next-themes'

const DARK_OPTIONS: ISourceOptions = {
  fullScreen: false,
  fpsLimit: 60,
  pauseOnBlur: true,
  detectRetina: true,
  particles: {
    number: { value: 250, density: { enable: true, width: 1920, height: 1080 } },
    color: { value: ['#ffffff', '#c4b5fd', '#93c5fd', '#f9a8d4'] },
    opacity: {
      value: { min: 0.1, max: 0.6 },
      animation: { enable: true, speed: 0.5, sync: false },
    },
    size: { value: { min: 0.5, max: 2.5 } },
    move: {
      enable: true,
      speed: 0.3,
      direction: 'none',
      random: true,
      straight: false,
      outModes: 'out',
    },
    links: { enable: false },
  },
  interactivity: {
    events: {
      onHover: { enable: true, mode: 'repulse' },
    },
    modes: {
      repulse: { distance: 80, duration: 0.4 },
    },
  },
}

const LIGHT_OPTIONS: ISourceOptions = {
  fullScreen: false,
  fpsLimit: 30,
  pauseOnBlur: true,
  detectRetina: true,
  particles: {
    number: { value: 100, density: { enable: true, width: 1920, height: 1080 } },
    color: { value: ['#18181b', '#71717a', '#a1a1aa'] },
    opacity: {
      value: { min: 0.1, max: 0.3 },
      animation: { enable: true, speed: 0.3, sync: false },
    },
    size: { value: { min: 0.5, max: 2 } },
    move: {
      enable: true,
      speed: 0.2,
      direction: 'none',
      random: true,
      straight: false,
      outModes: 'out',
    },
    links: { enable: false },
  },
  interactivity: {
    events: {
      onHover: { enable: false },
    },
  },
}

export function CosmicBackground() {
  const { resolvedTheme } = useTheme()
  const [ready, setReady] = useState(false)

  const isDark = resolvedTheme === 'dark'

  useEffect(() => {
    initParticlesEngine(async (engine) => {
      await loadSlim(engine)
    }).then(() => setReady(true))
  }, [])

  const options = useMemo(() => (isDark ? DARK_OPTIONS : LIGHT_OPTIONS), [isDark])

  return (
    <div className="fixed inset-0 z-0 overflow-hidden">
      {/* Base background */}
      <div className="absolute inset-0 bg-background" />
      <div className="dark:block hidden absolute inset-0 bg-[#050015]" />

      {/* Nebula gradients */}
      <div className="absolute inset-0 pointer-events-none">
        <div
          className="absolute inset-0 animate-nebula-drift opacity-100 dark:opacity-100"
          style={{
            background: isDark
              ? 'radial-gradient(ellipse at 80% 20%, rgba(123,97,255,0.15) 0%, transparent 50%), radial-gradient(ellipse at 20% 80%, rgba(0,212,255,0.1) 0%, transparent 50%), radial-gradient(ellipse at 50% 50%, rgba(255,107,157,0.08) 0%, transparent 40%)'
              : 'radial-gradient(ellipse at 80% 20%, rgba(123,97,255,0.04) 0%, transparent 50%), radial-gradient(ellipse at 20% 80%, rgba(0,212,255,0.03) 0%, transparent 50%)',
          }}
        />
      </div>

      {/* Shooting stars */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="shooting-star shooting-star-1" />
        <div className="shooting-star shooting-star-2" />
        <div className="shooting-star shooting-star-3" />
      </div>

      {/* Particles */}
      {ready && (
        <Particles
          id="cosmic-particles"
          className="!absolute !inset-0"
          options={options}
        />
      )}
    </div>
  )
}
