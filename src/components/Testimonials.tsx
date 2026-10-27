import { motion } from "framer-motion";
import { Star, Quote } from "lucide-react";

const TESTIMONIALS = [
  {
    name: "Prajwal Ambure",
    location: "Bengaluru",
    text: "After joining Divine Code 369, my business tripled in 3 months! The 369 manifestation technique is real and incredibly powerful.",
    initials: "PA"
  },
  {
    name: "Amol Hanchate",
    location: "Pune",
    text: "I was skeptical at first, but the numerology session changed my entire perspective. My career skyrocketed after aligning with my numbers.",
    initials: "AH"
  },
  {
    name: "Bhushan khairnar",
    location: "Buldhana",
    text: "The wealth attraction course opened my mind to true abundance. I manifested my dream home within 6 months of applying the techniques!",
    initials: "BK"
  },
  {
    name: "Nagesh lokhande",
    location: "Latur",
    text: "Personal guidance from the institute helped me align with my true purpose. I finally feel clear and confident. Highly recommended!",
    initials: "NL"
  }
];

export function Testimonials() {
  return (
    <section id="testimonials" className="py-24 relative z-10 bg-gradient-to-b from-transparent to-black/80">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <h2 className="text-sm font-semibold tracking-widest text-primary uppercase mb-3">Success Stories</h2>
          <h3 className="text-4xl md:text-5xl font-display font-bold text-white">What Our Students Say</h3>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {TESTIMONIALS.map((testimonial, idx) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: idx * 0.1 }}
              className="glass-card rounded-2xl p-6 relative"
            >
              <Quote size={40} className="absolute top-4 right-4 text-white/5" />
              <div className="flex gap-1 mb-4">
                {[1, 2, 3, 4, 5].map((star) => (
                  <Star key={star} size={16} className="fill-primary text-primary" />
                ))}
              </div>
              <p className="text-white/80 text-sm leading-relaxed mb-6 italic relative z-10">
                "{testimonial.text}"
              </p>
              <div className="flex items-center gap-3 mt-auto">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary to-[#996515] flex items-center justify-center text-background font-bold text-sm shadow-[0_0_10px_rgba(255,215,0,0.3)]">
                  {testimonial.initials}
                </div>
                <div>
                  <div className="text-white font-semibold text-sm">{testimonial.name}</div>
                  <div className="text-white/50 text-xs">{testimonial.location}</div>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
