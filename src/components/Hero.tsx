import { motion } from "framer-motion";
import { Sparkles, ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";

// Star field component for background
const Stars = () => {
  const [stars, setStars] = useState<{ id: number; top: string; left: string; size: number; duration: number; delay: number }[]>([]);

  useEffect(() => {
    const generatedStars = Array.from({ length: 50 }).map((_, i) => ({
      id: i,
      top: `${Math.random() * 100}%`,
      left: `${Math.random() * 100}%`,
      size: Math.random() * 3 + 1,
      duration: Math.random() * 3 + 2,
      delay: Math.random() * 5,
    }));
    setStars(generatedStars);
  }, []);

  return (
    <div className="stars-bg">
      {stars.map((star) => (
        <div
          key={star.id}
          className="star"
          style={{
            top: star.top,
            left: star.left,
            width: `${star.size}px`,
            height: `${star.size}px`,
            '--duration': `${star.duration}s`,
            '--delay': `${star.delay}s`,
          } as React.CSSProperties}
        />
      ))}
    </div>
  );
};

export function Hero() {
  return (
    <section id="home" className="relative min-h-screen flex items-center justify-center pt-20 overflow-hidden">
      {/* Background Images & Overlays */}
      <div className="absolute inset-0 z-0">
        <img
          src={`${import.meta.env.BASE_URL}images/hero-bg.png`}
          alt="Cosmic Background"
          className="w-full h-full object-cover opacity-40"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-black/20 via-black/60 to-background" />
      </div>
      
      <Stars />

      {/* Massive Glowing 369 in background */}
      <motion.div 
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 0.05, scale: 1 }}
        transition={{ duration: 2, ease: "easeOut" }}
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-0 pointer-events-none w-full flex justify-center overflow-hidden"
      >
        <span className="text-[30vw] font-display font-bold text-primary leading-none mix-blend-plus-lighter blur-[2px]">
          369
        </span>
      </motion.div>

      {/* Sacred Geometry Pattern */}
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 120, repeat: Infinity, ease: "linear" }}
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] opacity-10 z-0 pointer-events-none"
      >
        <img
          src={`${import.meta.env.BASE_URL}images/sacred-pattern.png`}
          alt=""
          className="w-full h-full object-contain"
        />
      </motion.div>

      {/* Content */}
      <div className="relative z-10 max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col items-center text-center">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
          className="mb-8"
        >
          <div className="w-24 h-24 md:w-32 md:h-32 mx-auto rounded-full p-1 bg-gradient-to-b from-primary/50 to-transparent shadow-[0_0_30px_rgba(255,215,0,0.3)] relative group cursor-pointer mb-6">
            <div className="absolute inset-0 rounded-full animate-spin-slow border border-primary/30 border-t-primary border-l-transparent" />
            <img
              src={`${import.meta.env.BASE_URL}logo.jpeg`}
              alt="Divine Code 369 Logo"
              className="w-full h-full object-cover rounded-full"
            />
          </div>
          
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass border-primary/30 text-primary/90 text-sm font-medium mb-6">
            <Sparkles size={16} className="text-primary" />
            <span className="tracking-widest uppercase text-xs">Unlock The Divine Code</span>
            <Sparkles size={16} className="text-primary" />
          </div>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.4 }}
          className="text-5xl md:text-7xl lg:text-8xl font-display font-bold text-white mb-6 leading-tight"
        >
          Divine Code <span className="text-gradient-gold">369</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.6 }}
          className="text-lg md:text-xl text-white/70 max-w-2xl mx-auto mb-8 font-light"
        >
          Reprogram your reality, harness the frequency of the universe, and manifest limitless abundance through ancient numerology and sacred energy codes.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.8 }}
          className="flex flex-col sm:flex-row items-center gap-4 text-sm text-white/50 tracking-wider uppercase mb-10"
        >
          <span>Numerology</span>
          <span className="hidden sm:inline">•</span>
          <span>Manifestation</span>
          <span className="hidden sm:inline">•</span>
          <span>369 Energy</span>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 1 }}
          className="flex flex-col sm:flex-row gap-4 w-full sm:w-auto"
        >
          <a
            href="#courses"
            className="group px-8 py-4 bg-primary text-primary-foreground rounded-full font-semibold text-lg flex items-center justify-center gap-2 hover:bg-primary/90 transition-all duration-300 shadow-[0_0_20px_rgba(255,215,0,0.4)] hover:shadow-[0_0_30px_rgba(255,215,0,0.6)] hover:-translate-y-1"
          >
            Join Now
            <ArrowRight size={20} className="group-hover:translate-x-1 transition-transform" />
          </a>
          <a
            href="#contact"
            className="px-8 py-4 bg-transparent text-white border-2 border-primary/50 rounded-full font-semibold text-lg hover:border-primary hover:bg-primary/10 transition-all duration-300 hover:-translate-y-1"
          >
            Book Consultation
          </a>
        </motion.div>
      </div>

      {/* Scroll indicator */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1, delay: 1.5 }}
        className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2"
      >
        <span className="text-white/40 text-xs tracking-widest uppercase">Scroll</span>
        <div className="w-[1px] h-12 bg-gradient-to-b from-primary/50 to-transparent animate-pulse" />
      </motion.div>
    </section>
  );
}
