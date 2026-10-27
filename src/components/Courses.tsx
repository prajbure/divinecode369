import { motion } from "framer-motion";
import { BookOpen, Sparkles, Fingerprint, Diamond, ArrowRight } from "lucide-react";

const COURSES = [
  {
    icon: Fingerprint,
    title: "Numerology Mastery",
    description: "Decode your divine numbers and life path. Understand your karmic lessons and hidden potential.",
    tag: "Most Popular",
    waMessage: "Hello%20Divine%20Code%20369%2C%20I%20am%20interested%20in%20enrolling%20in%20the%20*Numerology%20Mastery%20Course*%20%F0%9F%94%AE.%20Please%20share%20the%20details%20and%20fees."
  },
  {
    icon: Sparkles,
    title: "369 Manifestation",
    description: "Master Nikola Tesla's sacred manifestation method. Learn the energetic rhythm to shape reality.",
    tag: "Core Practice",
    waMessage: "Hello%20Divine%20Code%20369%2C%20I%20am%20interested%20in%20enrolling%20in%20the%20*369%20Manifestation%20Technique%20Course*%20%E2%9C%A8.%20Please%20share%20the%20details%20and%20fees."
  },
  {
    icon: BookOpen,
    title: "Mind Reprogramming",
    description: "Rewire limiting beliefs at the deepest level. Remove mental blocks holding you back.",
    tag: "Deep Work",
    waMessage: "Hello%20Divine%20Code%20369%2C%20I%20am%20interested%20in%20enrolling%20in%20the%20*Subconscious%20Mind%20Reprogramming%20Course*%20%F0%9F%A7%A0.%20Please%20share%20the%20details%20and%20fees."
  },
  {
    icon: Diamond,
    title: "Wealth Blueprint",
    description: "Create magnetic abundance using specific energy codes tailored for financial freedom.",
    tag: "Advanced",
    waMessage: "Hello%20Divine%20Code%20369%2C%20I%20am%20interested%20in%20enrolling%20in%20the%20*Wealth%20Attraction%20Blueprint%20Course*%20%F0%9F%92%8E.%20Please%20share%20the%20details%20and%20fees."
  }
];

export function Courses() {
  return (
    <section id="courses" className="py-24 relative z-10 bg-black/40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-16 gap-6">
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="max-w-2xl"
          >
            <h2 className="text-sm font-semibold tracking-widest text-primary uppercase mb-3">Transform Your Life</h2>
            <h3 className="text-4xl md:text-5xl font-display font-bold text-white mb-4">Our Sacred Courses</h3>
            <p className="text-white/70">
              Structured programs designed to elevate your frequency, clear blockages, and align you with the universe's ultimate code of abundance.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <a
              href="https://wa.me/919923675228?text=Hello%20Divine%20Code%20369%2C%20I%20would%20like%20to%20know%20more%20about%20your%20courses%20and%20the%20full%20syllabus."
              target="_blank"
              rel="noreferrer"
              className="text-primary hover:text-white transition-colors flex items-center gap-2 font-medium"
            >
              Request Full Syllabus <ArrowRight size={16} />
            </a>
          </motion.div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {COURSES.map((course, idx) => (
            <motion.div
              key={course.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: idx * 0.1 }}
              className="group glass-card rounded-2xl p-8 relative overflow-hidden flex flex-col sm:flex-row gap-6 items-start"
            >
              <div className="absolute top-0 right-0 w-32 h-32 bg-primary/20 blur-[50px] opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-full" />

              <div className="flex-shrink-0 w-16 h-16 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center group-hover:border-primary/50 group-hover:text-primary transition-all duration-300">
                <course.icon size={28} className="text-white/80 group-hover:text-primary transition-colors" />
              </div>

              <div className="flex-1">
                <div className="text-xs font-bold tracking-wider text-primary/80 uppercase mb-2">
                  {course.tag}
                </div>
                <h4 className="text-2xl font-display font-bold text-white mb-2">{course.title}</h4>
                <p className="text-white/60 mb-6 text-sm leading-relaxed">{course.description}</p>

                <a
                  href={`https://wa.me/919923675228?text=${course.waMessage}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white text-sm font-medium hover:bg-primary hover:text-primary-foreground hover:border-primary transition-all duration-300"
                >
                  Enroll Now
                </a>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
