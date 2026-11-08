import type { PropsWithChildren } from 'react';
import { ShieldCheck } from 'lucide-react';

interface AuthPageFrameProps extends PropsWithChildren {
  eyebrow: string;
  title: string;
  subtitle: string;
}

export function AuthPageFrame({ eyebrow, title, subtitle, children }: AuthPageFrameProps) {
  return (
    <main className="auth-screen">
      <div className="auth-frame">
        <div className="auth-brand-lockup">
          <span className="auth-brand-mark"><ShieldCheck size={22} strokeWidth={2.2} /></span>
          <span>
            <strong>PrivaCheck</strong>
            <small>COMPLIANCE WORKSPACE</small>
          </span>
        </div>
        <section className="auth-card">
          <div className="auth-eyebrow">{eyebrow}</div>
          <h1>{title}</h1>
          <p className="auth-subtitle">{subtitle}</p>
          {children}
        </section>
        <p className="auth-disclaimer">
          PrivaCheck · Automated findings are technical indicators, not legal advice.
        </p>
      </div>
    </main>
  );
}
