import { QRCodeSVG } from 'qrcode.react';

interface QRCodeOverlayProps {
  url: string;
  size?: number;
}

export function QRCodeOverlay({ url, size = 200 }: QRCodeOverlayProps) {
  return (
    <div className="qr-overlay">
      <div className="qr-panel">
        <QRCodeSVG
          value={url}
          size={size}
          fgColor="#ffffff"
          bgColor="#1e1e1e"
        />
        <p className="qr-url-label">{url}</p>
      </div>
    </div>
  );
}
