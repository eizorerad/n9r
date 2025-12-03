"use client";

import React from "react";

const FlyingGhost = () => {
    return (
        <div className="fixed z-50 pointer-events-none animate-ghost-fly top-1/3 right-0">
            <svg
                width="80"
                height="80"
                viewBox="0 0 16 16"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                className="drop-shadow-lg image-pixelated opacity-90"
                style={{ imageRendering: "pixelated" }}
            >
                {/* Outline/Shadow (Darker) */}
                <rect x="4" y="1" width="8" height="14" fill="#e2e8f0" />
                <rect x="2" y="3" width="12" height="10" fill="#e2e8f0" />

                {/* Ghost Body (White) */}
                <rect x="5" y="2" width="6" height="12" fill="#ffffff" />
                <rect x="3" y="4" width="10" height="8" fill="#ffffff" />
                <rect x="4" y="3" width="8" height="10" fill="#ffffff" />

                {/* Tail/Bottom Details */}
                <rect x="3" y="12" width="2" height="1" fill="#ffffff" />
                <rect x="7" y="12" width="2" height="1" fill="#ffffff" />
                <rect x="11" y="12" width="2" height="1" fill="#ffffff" />

                {/* Eyes (Black) */}
                <rect x="5" y="6" width="2" height="2" fill="#000000" />
                <rect x="9" y="6" width="2" height="2" fill="#000000" />

                {/* Blush (Pink) - for cuteness/spookiness mix */}
                <rect x="4" y="8" width="1" height="1" fill="#fbcfe8" />
                <rect x="11" y="8" width="1" height="1" fill="#fbcfe8" />

            </svg>
            <style jsx>{`
        @keyframes ghost-fly {
          0% {
            transform: translateX(20vw) translateY(0) scale(1);
            opacity: 0;
          }
          10% {
            opacity: 0.9;
          }
          25% {
            transform: translateX(-25vw) translateY(-20px) scale(1.05);
          }
          50% {
            transform: translateX(-60vw) translateY(10px) scale(1);
            opacity: 0.7;
          }
          75% {
            transform: translateX(-85vw) translateY(-15px) scale(1.05);
          }
          90% {
            opacity: 0.9;
          }
          100% {
            transform: translateX(-120vw) translateY(0) scale(1);
            opacity: 0;
          }
        }
        .animate-ghost-fly {
          animation: ghost-fly 25s linear infinite;
          animation-delay: 5s; /* Start after pumpkin */
        }
      `}</style>
        </div>
    );
};

export default FlyingGhost;
