import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, useDraggable, useDroppable, useSensor, useSensors } from '@dnd-kit/core'
import { DotsSixVertical } from '@phosphor-icons/react'
import { Page } from '../components/Page'
import { createProject, listProjects, setStage } from '../api/projects'
import { errorMessage } from '../api/client'
import { parseDate } from '../lib/format'
import { btn, card, errorText, field, skeleton } from '../components/ui'

const STAGES = [
  ['idea', 'Idea'], ['scripting', 'Scripting'], ['recording', 'Recording'], ['editing', 'Editing'],
  ['review', 'Review'], ['scheduled', 'Scheduled'], ['published', 'Published'],
]
const LABEL = Object.fromEntries(STAGES)

function CardBody({ project, handle, floating = false }) {
  return (
    <div className={`flex items-start gap-2 p-3 ${card} ${floating ? 'shadow-[0_8px_24px_rgba(32,32,32,0.08)]' : ''}`}>
      {handle}
      <div className="min-w-0">
        <Link to={`/projects/${project.id}`} className="block rounded-xs text-[15px] font-semibold leading-snug hover:underline hover:underline-offset-4 focus-ring">
          {project.title}
        </Link>
        <p className="mt-1.5 text-xs text-mute">
          Updated {parseDate(project.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
        </p>
      </div>
    </div>
  )
}

function Card({ project }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: project.id, data: { project } })
  const handle = (
    <button
      {...listeners}
      {...attributes}
      aria-label={`Move ${project.title}. Currently in ${LABEL[project.stage]}.`}
      className="mt-0.5 -ml-1 shrink-0 cursor-grab touch-none rounded-xs text-stone hover:text-ink focus-ring active:cursor-grabbing"
    >
      <DotsSixVertical size={18} weight="bold" />
    </button>
  )
  return (
    <li ref={setNodeRef} className={isDragging ? 'opacity-40' : ''}>
      <CardBody project={project} handle={handle} />
    </li>
  )
}

function Column({ stage, label, projects }) {
  const { setNodeRef, isOver } = useDroppable({ id: stage })
  return (
    <section
      ref={setNodeRef}
      aria-label={`${label}, ${projects.length} projects`}
      className={`flex min-w-40 flex-1 flex-col rounded-lg border p-2.5 transition-colors ${isOver ? 'border-hairline-strong bg-card' : 'border-transparent bg-bone'}`}
    >
      <h2 className="flex items-center justify-between px-1.5 pt-1 pb-3 text-sm font-semibold">
        {label}
        <span className="font-mono text-xs font-normal text-mute tabular-nums">{projects.length}</span>
      </h2>
      <ul className="flex min-h-24 flex-1 flex-col gap-2">
        {projects.map((p) => <Card key={p.id} project={p} />)}
      </ul>
    </section>
  )
}

export default function ProjectBoard() {
  const navigate = useNavigate()
  const autoFocus = !!useLocation().state?.create
  const [projects, setProjects] = useState(null)
  const [title, setTitle] = useState('')
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(null)
  // distance: a click on the title link still navigates; keyboard: space to lift, arrows to move, space to drop
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor))

  useEffect(() => {
    listProjects().then(setProjects).catch((e) => setError(errorMessage(e, 'Could not load projects.')))
  }, [])

  const create = async (e) => {
    e.preventDefault()
    try {
      const p = await createProject({ title })
      navigate(`/projects/${p.id}`)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const drop = async ({ active, over }) => {
    setDragging(null)
    const project = active.data.current.project
    if (!over || over.id === project.stage) return
    const before = projects
    setProjects((list) => list.map((p) => (p.id === project.id ? { ...p, stage: over.id } : p))) // optimistic
    try {
      const updated = await setStage(project.id, over.id)
      setProjects((list) => list.map((p) => (p.id === updated.id ? updated : p)))
    } catch (err) {
      setProjects(before)
      setError(errorMessage(err, 'Could not move the project.'))
    }
  }

  return (
    <Page title="Projects" description="Track each piece of content from idea to published. Drag a card to change its stage.">
      <form onSubmit={create} className="flex max-w-2xl flex-col gap-3 sm:flex-row sm:items-end">
        <label className="grid flex-1 gap-2 text-sm font-semibold">
          New project
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            autoFocus={autoFocus}
            placeholder="Name your next video"
            className={field}
          />
        </label>
        <button className={btn.primary}>
          Create
        </button>
      </form>
      {error && <p role="alert" className={`mt-3 ${errorText}`}>{error}</p>}

      <div className="mt-10 -mx-4 overflow-x-auto px-4 pb-4 md:-mx-6 md:px-6">
        {projects === null ? (
          <div className="flex gap-3">
            {STAGES.map(([s]) => <div key={s} className={`h-56 min-w-40 flex-1 ${skeleton}`} />)}
          </div>
        ) : (
          <DndContext sensors={sensors} onDragStart={({ active }) => setDragging(active.data.current.project)} onDragEnd={drop} onDragCancel={() => setDragging(null)}>
            <div className="flex gap-3">
              {STAGES.map(([stage, label]) => (
                <Column key={stage} stage={stage} label={label} projects={projects.filter((p) => p.stage === stage)} />
              ))}
            </div>
            <DragOverlay dropAnimation={null}>
              {dragging && <div className="w-48 rotate-2"><CardBody project={dragging} floating /></div>}
            </DragOverlay>
          </DndContext>
        )}
      </div>
    </Page>
  )
}
