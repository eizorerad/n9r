"use client";

import React from "react";

const FlyingPumpkin = () => {
    return (
        <div className="fixed z-50 pointer-events-none animate-fly top-1/4 left-0">
            <svg
                width="80"
                height="80"
                viewBox="0 0 16 16"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                className="drop-shadow-lg image-pixelated"
                style={{ imageRendering: "pixelated" }}
            >
                {/* Outline/Dark Background */}
                <rect x="4" y="2" width="8" height="12" fill="#431407" />
                <rect x="2" y="4" width="12" height="8" fill="#431407" />

                {/* Pumpkin Body (Orange) */}
                <rect x="5" y="3" width="6" height="10" fill="#ea580c" />
                <rect x="3" y="5" width="10" height="6" fill="#ea580c" />
                <rect x="4" y="4" width="8" height="8" fill="#ea580c" />

                {/* Shading (Darker Orange) */}
                <rect x="4" y="10" width="8" height="1" fill="#c2410c" />
                <rect x="5" y="11" width="6" height="1" fill="#c2410c" />

                {/* Stem (Green) */}
                <rect x="7" y="0" width="2" height="3" fill="#15803d" />
                <rect x="9" y="1" width="1" height="1" fill="#15803d" />

                {/* Evil Eyes (Glowing Yellow/Red) */}
                <rect x="4" y="6" width="2" height="1" fill="#fef08a" />
                <rect x="5" y="7" width="1" height="1" fill="#fef08a" />

                <rect x="10" y="6" width="2" height="1" fill="#fef08a" />
                <rect x="10" y="7" width="1" height="1" fill="#fef08a" />

                {/* Evil Mouth (Jagged) */}
                <rect x="4" y="9" width="1" height="1" fill="#451a03" />
                <rect x="5" y="10" width="1" height="1" fill="#451a03" />
                <rect x="6" y="9" width="1" height="1" fill="#451a03" />
                <rect x="7" y="10" width="2" height="1" fill="#451a03" />
                <rect x="9" y="9" width="1" height="1" fill="#451a03" />
                <rect x="10" y="10" width="1" height="1" fill="#451a03" />
                <rect x="11" y="9" width="1" height="1" fill="#451a03" />

            </svg>
            <style jsx>{`
        @keyframes fly {
          0% {
            transform: translateX(-20vw) translateY(0) scale(1);
          }
          25% {
            transform: translateX(25vw) translateY(-40px) scale(1.1);
          }
          50% {
            transform: translateX(60vw) translateY(20px) scale(1);
          }
          75% {
            transform: translateX(85vw) translateY(-30px) scale(1.1);
          }
          100% {
            transform: translateX(120vw) translateY(0) scale(1);
          }
        }
        .animate-fly {
          animation: fly 15s linear infinite;
        }
      `}</style>
        </div>
    );
};

export default FlyingPumpkin;
