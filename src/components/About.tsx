import { motion } from "framer-motion";
import { Coins, Brain, Infinity } from "lucide-react";

const ABOUT_CARDS = [
  {
    icon: Coins,
    title: "Wealth Attraction",
    description: "Align your internal energy with financial abundance. Clear blockages and become a magnet for prosperity."
  },
  {
    icon: Brain,
    title: "Success Mindset",
    description: "Reprogram limiting beliefs at the subconscious level for peak performance and unwavering confidence."
  },
  {
    icon: Infinity,
    title: "Abundance Energy",
    description: "Harness the sacred 369 frequency to unlock unlimited growth in your personal and professional life."
  }
];

export function About() {
  return (
    <section id="about" className="py-24 relative z-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <h2 className="text-sm font-semibold tracking-widest text-primary uppercase mb-3">The Journey Begins Here</h2>
          <h3 className="text-4xl md:text-5xl font-display font-bold text-white mb-6">About Divine Code <span className="text-primary">369</span></h3>
          <p className="text-white/70 max-w-3xl mx-auto text-lg leading-relaxed">
            We are dedicated to helping you awaken your true potential. Through the sacred sciences of numerology, the powerful 369 manifestation technique, and deep subconscious reprogramming, we guide you from where you are to where you are destined to be.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {ABOUT_CARDS.map((card, idx) => (
            <motion.div
              key={card.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-50px" }}
              transition={{ duration: 0.6, delay: idx * 0.2 }}
              className="glass-card rounded-2xl p-8 text-center group"
            >
              <div className="w-16 h-16 mx-auto rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center mb-6 group-hover:bg-primary/20 group-hover:scale-110 transition-all duration-300">
                <card.icon size={32} className="text-primary" />
              </div>
              <h4 className="text-xl font-display font-bold text-white mb-3">{card.title}</h4>
              <p className="text-white/60 text-sm leading-relaxed">{card.description}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
