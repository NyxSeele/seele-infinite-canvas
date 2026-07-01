import { useMemo } from "react"

import { ensureMediaUrl } from "../../utils/mediaTicket"

import { useLocale } from "../../utils/locale"

import "./CastMentionPicker.css"



const sp = (e) => e.stopPropagation()



export default function CastMentionPicker({ open, items = [], onSelect, onClose }) {

  const { t } = useLocale()

  const list = useMemo(() => items.filter((c) => c?.name), [items])



  if (!open) return null



  return (

    <div className="cast-mention-picker nodrag nopan" onPointerDown={sp}>

      {list.length === 0 ? (

        <div className="cast-mention-empty">

          {t("canvas.cast.noItems")}

        </div>

      ) : (

        list.map((item) => (

          <button

            key={item.id}

            type="button"

            className="cast-mention-item nodrag"

            onMouseDown={(e) => {

              e.preventDefault()

              onSelect?.(item)

              onClose?.()

            }}

          >

            {item.imageUrl ? (

              <img

                src={ensureMediaUrl(item.imageUrl)}

                alt=""

                className="cast-mention-thumb"

                draggable={false}

              />

            ) : (

              <span className="cast-mention-thumb cast-mention-thumb--placeholder">

                {item.type === "scene" ? t("canvas.asset.sceneTag") : t("canvas.asset.personTag")}

              </span>

            )}

            <span className="cast-mention-meta">

              <span className="cast-mention-name">@{item.name}</span>

              <span className="cast-mention-type">

                {item.source === "global"

                  ? t("canvas.cast.fromAssetLib", {

                      type: item.type === "scene"

                        ? t("canvas.script.scene")

                        : t("canvas.script.person"),

                    })

                  : item.type === "scene"

                    ? t("canvas.cast.sceneSetting")

                    : t("canvas.cast.charSetting")}

              </span>

            </span>

          </button>

        ))

      )}

    </div>

  )

}

