import { Sparkles, Instagram, MessageCircle } from "lucide-react";

export function Footer() {
  return (
    <footer className="border-t border-white/5 bg-background relative z-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="flex flex-col md:flex-row items-center justify-between gap-6">

          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full overflow-hidden border border-primary/30">
              <img
                src={`${import.meta.env.BASE_URL}logo.jpeg`}
                alt="Divine Code 369"
                className="w-full h-full object-cover"
              />
            </div>
            <span className="font-display font-bold text-xl text-white">Divine Code <span className="text-primary">369</span></span>
          </div>

          <div className="flex flex-wrap justify-center gap-x-8 gap-y-2 text-sm text-white/50">
            <a href="#home" className="hover:text-primary transition-colors">Home</a>
            <a href="#about" className="hover:text-primary transition-colors">About</a>
            <a href="#courses" className="hover:text-primary transition-colors">Courses</a>
            <a href="#trainer" className="hover:text-primary transition-colors">Trainer</a>
            <a href="#testimonials" className="hover:text-primary transition-colors">Testimonials</a>
            <a href="#contact" className="hover:text-primary transition-colors">Contact</a>
          </div>

          <div className="flex items-center gap-3">
            <a
              href="https://wa.me/919923675228?text=Hello%20Divine%20Code%20369%2C%20I%20am%20interested%20in%20your%20services."
              target="_blank"
              rel="noreferrer"
              aria-label="WhatsApp"
              className="w-9 h-9 rounded-full bg-[#25D366]/20 border border-[#25D366]/30 flex items-center justify-center text-[#25D366] hover:bg-[#25D366] hover:text-white transition-all duration-300"
            >
              <MessageCircle size={16} />
            </a>
            <a
              href="https://www.instagram.com/divine.code_369?utm_source=qr&igsh=bnA1MzZqZ3Axcmxu"
              target="_blank"
              rel="noreferrer"
              aria-label="Instagram"
              className="w-9 h-9 rounded-full bg-pink-500/10 border border-pink-500/20 flex items-center justify-center text-pink-400 hover:bg-gradient-to-tr hover:from-[#f09433] hover:via-[#e6683c] hover:to-[#bc1888] hover:text-white hover:border-transparent transition-all duration-300"
            >
              <Instagram size={16} />
            </a>
          </div>
        </div>

        <div className="mt-12 pt-8 border-t border-white/5 flex flex-col md:flex-row items-center justify-between text-xs text-white/40 gap-4">
          <p>© {new Date().getFullYear()} Divine Code 369. All Rights Reserved.</p>
          <div className="flex items-center gap-2">
            Made with <Sparkles size={12} className="text-primary" /> using Sacred Numbers
          </div>
        </div>
      </div>
    </footer>
  );
}
