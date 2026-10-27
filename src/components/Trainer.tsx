import { motion } from "framer-motion";
import { Award } from "lucide-react";

export function Trainer() {
  return (
    <section id="trainer" className="py-24 relative z-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <h2 className="text-sm font-semibold tracking-widest text-primary uppercase mb-3">Meet Your Guide</h2>
          <h3 className="text-4xl md:text-5xl font-display font-bold text-white mb-4">
            Your <span className="text-gradient-gold">Trainer</span>
          </h3>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center mb-16">
          {/* Trainer Image */}
          <motion.div
            initial={{ opacity: 0, x: -40 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.7 }}
            className="relative flex justify-center"
          >
            <div className="relative w-full max-w-sm mx-auto">
              {/* Glow ring */}
              <div className="absolute -inset-4 rounded-3xl bg-gradient-to-br from-primary/30 via-transparent to-primary/10 blur-2xl" />
              <div className="absolute -inset-[2px] rounded-3xl bg-gradient-to-br from-primary/50 to-transparent" />
              <img
                src={`${import.meta.env.BASE_URL}trainer.png`}
                alt="Shubham Khamitkar - Trainer"
                className="relative w-full rounded-3xl object-cover shadow-2xl"
              />
            </div>
          </motion.div>

          {/* Trainer Details */}
          <motion.div
            initial={{ opacity: 0, x: 40 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.7 }}
            className="space-y-6"
          >
            <div>
              <h4 className="text-4xl font-display font-bold text-white mb-1">Shubham Khamitkar</h4>
              <p className="text-primary font-semibold text-lg">Trader · Manifestation Coach · Numerologist</p>
            </div>

            <p className="text-white/70 text-lg leading-relaxed">
              Shubham Khamitkar is a certified numerologist and manifestation coach who has helped hundreds of people align with the universe's sacred codes. Trained under the prestigious <strong className="text-white">Occult Gyaanshala</strong> — ISO 9001:2015 certified — he brings a powerful blend of ancient wisdom and modern practicality.
            </p>

            <p className="text-white/70 leading-relaxed">
              With expertise in stock market trading, the 369 manifestation technique, and subconscious reprogramming, Shubham bridges the gap between spiritual growth and real-world financial abundance. His sessions are transformational, practical, and tailored for every individual.
            </p>

            <div className="flex flex-wrap gap-3 pt-2">
              {["Numerology", "369 Manifestation", "Subconscious Reprogramming", "Wealth Attraction", "Stock Trading"].map((skill) => (
                <span key={skill} className="px-4 py-1.5 rounded-full glass border border-primary/30 text-primary text-sm font-medium">
                  {skill}
                </span>
              ))}
            </div>

            <a
              href="https://wa.me/919923675228?text=Hello%20Shubham%20sir%2C%20I%20would%20like%20to%20know%20more%20about%20your%20courses%20and%20book%20a%20consultation%20with%20you."
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 mt-2 px-8 py-4 rounded-full bg-primary text-primary-foreground font-bold text-lg shadow-[0_0_20px_rgba(255,215,0,0.4)] hover:shadow-[0_0_30px_rgba(255,215,0,0.7)] hover:-translate-y-1 transition-all duration-300"
            >
              Book a Session
            </a>
          </motion.div>
        </div>

        {/* Certificate */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7 }}
          className="text-center"
        >
          <h4 className="text-2xl font-display font-bold text-white mb-3">Official Certification</h4>
          <p className="text-white/60 mb-8">Certified by Occult Gyaanshala — ISO 9001:2015 Recognised Institute</p>
          <div className="relative inline-block">
            <div className="absolute -inset-3 rounded-2xl bg-gradient-to-br from-primary/30 to-transparent blur-xl" />
            <div className="absolute -inset-[2px] rounded-2xl bg-gradient-to-br from-primary/40 to-transparent" />
            <img
              src={`${import.meta.env.BASE_URL}certificate.png`}
              alt="Trainer Certificate - Shubham Khamitkar"
              className="relative rounded-2xl max-w-2xl w-full mx-auto shadow-2xl"
            />
          </div>
        </motion.div>
      </div>
    </section>
  );
}
