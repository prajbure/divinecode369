import { motion } from "framer-motion";
import { Phone, MapPin, Mail, Instagram, MessageCircle } from "lucide-react";

export function Contact() {
  return (
    <section id="contact" className="py-24 relative z-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <h2 className="text-sm font-semibold tracking-widest text-primary uppercase mb-3">Get in Touch</h2>
            <h3 className="text-4xl md:text-5xl font-display font-bold text-white mb-6">Connect With Us</h3>
            <p className="text-white/70 mb-10 text-lg">
              Ready to decode your destiny? Reach out to us for consultations, course inquiries, or general guidance. Our team is here to illuminate your path.
            </p>

            <div className="space-y-6">
              <a href="tel:9923675228" className="flex items-center gap-4 group">
                <div className="w-12 h-12 rounded-full glass border-white/10 flex items-center justify-center group-hover:bg-primary/20 group-hover:border-primary/50 transition-colors">
                  <Phone className="text-primary" size={20} />
                </div>
                <div>
                  <div className="text-white/50 text-sm">Call Us</div>
                  <div className="text-white font-medium group-hover:text-primary transition-colors">+91 99236 75228</div>
                </div>
              </a>

              <div className="flex items-center gap-4 group">
                <div className="w-12 h-12 rounded-full glass border-white/10 flex items-center justify-center group-hover:bg-primary/20 group-hover:border-primary/50 transition-colors">
                  <MapPin className="text-primary" size={20} />
                </div>
                <div>
                  <div className="text-white/50 text-sm">Location</div>
                  <div className="text-white font-medium">Samta Nagar, Galli No. 1,<br />Famous Chowk, New Sangvi, Pune</div>
                </div>
              </div>

              <a href="mailto:info@divinecode369.in" className="flex items-center gap-4 group">
                <div className="w-12 h-12 rounded-full glass border-white/10 flex items-center justify-center group-hover:bg-primary/20 group-hover:border-primary/50 transition-colors">
                  <Mail className="text-primary" size={20} />
                </div>
                <div>
                  <div className="text-white/50 text-sm">Email</div>
                  <div className="text-white font-medium group-hover:text-primary transition-colors">info@divinecode369.in</div>
                </div>
              </a>
            </div>

            <div className="flex gap-4 mt-10">
              <a
                href="https://wa.me/919923675228?text=Hello%20Divine%20Code%20369%2C%20I%20am%20interested%20in%20your%20services.%20Please%20guide%20me."
                target="_blank"
                rel="noreferrer"
                className="flex-1 flex items-center justify-center gap-2 py-4 rounded-xl bg-[#25D366] text-white font-bold hover:bg-[#20bd5a] transition-colors shadow-[0_0_20px_rgba(37,211,102,0.3)] hover:-translate-y-1"
              >
                <MessageCircle size={20} /> WhatsApp
              </a>
              <a
                href="https://www.instagram.com/divine.code_369?utm_source=qr&igsh=bnA1MzZqZ3Axcmxu"
                target="_blank"
                rel="noreferrer"
                className="w-16 flex items-center justify-center rounded-xl glass border border-white/10 hover:bg-gradient-to-tr hover:from-[#f09433] hover:via-[#e6683c] hover:to-[#bc1888] transition-all duration-300 hover:text-white hover:border-transparent text-white/70 hover:-translate-y-1"
              >
                <Instagram size={24} />
              </a>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="relative h-[500px] rounded-3xl overflow-hidden glass border-white/10 flex items-center justify-center group"
          >
            <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1524661135-423995f22d0b?q=80&w=1000&auto=format&fit=crop')] bg-cover bg-center opacity-30 mix-blend-luminosity grayscale group-hover:grayscale-0 transition-all duration-700" />
            <div className="absolute inset-0 bg-gradient-to-t from-background via-transparent to-transparent" />

            <div className="relative z-10 glass px-6 py-4 rounded-2xl border-white/20 text-center shadow-[0_0_30px_rgba(255,215,0,0.1)]">
              <div className="w-16 h-16 mx-auto bg-primary text-background rounded-full flex items-center justify-center mb-3 animate-pulse-glow">
                <MapPin size={28} />
              </div>
              <h4 className="text-xl font-display font-bold text-white">Pune Headquarters</h4>
              <p className="text-white/70 text-sm">Divine Code 369 Institute</p>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
