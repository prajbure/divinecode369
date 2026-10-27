import { motion } from "framer-motion";
import { Zap, Target, Leaf, UserCircle } from "lucide-react";

const FEATURES = [
  {
    icon: Zap,
    title: "Practical Techniques",
    description: "No vague theories. You get step-by-step, actionable methods that deliver measurable changes."
  },
  {
    icon: Target,
    title: "Real Results",
    description: "Thousands of students have successfully manifested better careers, relationships, and health."
  },
  {
    icon: Leaf,
    title: "Simple Methods",
    description: "Designed for busy lives. Easy-to-follow daily practices that take only minutes to perform."
  },
  {
    icon: UserCircle,
    title: "Personal Guidance",
    description: "Get 1-on-1 consultations tailored to your unique numerological chart and life goals."
  }
];

export function Features() {
  return (
    <section id="why-us" className="py-24 relative z-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-16">
          <motion.h2 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-3xl md:text-4xl font-display font-bold text-white"
          >
            Why Choose <span className="text-primary">Divine Code 369</span>?
          </motion.h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
          {FEATURES.map((feature, idx) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: idx * 0.1 }}
              className="text-center"
            >
              <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-white/10 to-transparent border border-white/10 flex items-center justify-center mb-6 shadow-lg shadow-black/50 relative overflow-hidden group">
                <div className="absolute inset-0 bg-primary/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out" />
                <feature.icon size={32} className="text-primary relative z-10" />
              </div>
              <h4 className="text-lg font-bold text-white mb-2">{feature.title}</h4>
              <p className="text-white/60 text-sm">{feature.description}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
